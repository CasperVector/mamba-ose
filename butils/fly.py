import collections
import numpy
import re
from bluesky import plans, plan_stubs as bps, preprocessors as bpp
from .bubo import sseq_disable
from .panda import seq_disable, seq_outs_not
from .plans import cfg_trans, motors_get, norm_cache, norm_snake

PANDA_FREQ, DSEQ_DELAY = int(125e6), 9

def split_table(table, max_rows, atom_rows = 1, max_split = 0):
    n, = set(len(v) for k, v in table.items())
    m = max_rows // atom_rows * atom_rows
    n = int(numpy.ceil(n / m))
    n = min(n, max_split + 1) if max_split else n
    return [{k: (v[i * m : (i + 1) * m] if i + 1 < n else v[i * m:])
        for k, v in table.items()} for i in range(n)]

def auto_delay(tables):
    for i in range(len(tables) - 1):
        if tables[i + 1]["trigger"][0] == "Immediate":
            assert tables[i]["repeats"][-1] == 1 and \
                tables[i]["time2"][-1] > DSEQ_DELAY
            tables[i]["time2"][-1] -= DSEQ_DELAY
    return tables

def encoder_monitor(panda, inp):
    if not inp.startswith("inenc"):
        return []
    inp = re.sub(r"\.[^.]+$", "", inp)
    out = inp.replace("in", "out")
    return [
        ("%s.%s" % (out, f), ("%s.%s" % (inp, f)).upper())
        for f in ["a", "b", "z", "data", "val"]
    ] + [("%s.enable" % out, "ONE")]

def cfg_inputs(panda, inputs, dseq = False, **kwargs):
    cfg = []
    for i, (inp, motor) in enumerate(inputs):
        cfg += encoder_monitor(panda, inp)
        cfg += [("%s.capture" % inp, "Min Max Mean")]
        if i < 3:
            cfg += [("seq1.pos%s" % chr(ord("a") + i), inp.upper())]
            if dseq:
                cfg += [("seq2.pos%s" % chr(ord("a") + i), inp.upper())]
        if motor:
            getattr(panda, inp).bind(motor, **kwargs)
    return cfg

def prep_simple(panda, outputs, inputs, pgate = True, **kwargs):
    cfg = {
        "pcap.enable": "ZERO",
        "pcap.trig_edge": "Falling",
        "seq1.enable": "PCAP.ACTIVE"
    }
    cfg.update(cfg_inputs(panda, inputs, dseq = False, **kwargs))
    if pgate:
        outputs = [("pcap.gate", "a"), ("pcap.trig", "a")] + outputs
    for out in outputs:
        mux, out = out if isinstance(out, tuple) else (out, "b")
        cfg.update([(mux, "SEQ1.OUT" + out.upper())])
    panda.configure(cfg)

def prep_dseq(panda, outputs, inputs, pgate = True, **kwargs):
    cfg = panda.dseq.make_cfg()
    cfg.update(cfg_inputs(panda, inputs, dseq = True, **kwargs))
    luts = {}
    if pgate:
        outputs = [("pcap.gate", "a"), ("pcap.trig", "a")] + outputs
    for out in outputs:
        mux, out = out if isinstance(out, tuple) else (out, "b")
        luts[out] = ord(out) - ord("a") + 1
        cfg.update([(mux, "LUT%d.OUT" % luts[out])])
    for out in luts:
        cfg.update([
            ("lut%d.inpa" % luts[out], "SEQ1.OUT%s" % out.upper()),
            ("lut%d.inpb" % luts[out], "SEQ2.OUT%s" % out.upper()),
            ("lut%d.func" % luts[out], "A|B")
        ])
    panda.configure(cfg)

def prep_dshut(panda, outputs):
    cfg, luts = {}, {}
    for out in outputs:
        luts[out] = ord(out) - ord("a") + 1
        cfg["lut%d.inpc" % luts[out]] = "PCAP.ACTIVE"
    def set_mode(lut, mode):
        lut.func.value.put({"hard": "A|B", "soft": "D",
            "auto": "C?(A|B):D"}[mode])
    def set_state(lut, state):
        lut.inpd.value.put({"ZERO": "ZERO", "ONE": "ONE"}[state])
    def set_shutter(out, **kwargs):
        for o in out:
            l = getattr(panda, "lut%d" % luts[o])
            for k, v in kwargs.items():
                {"mode": set_mode, "state": set_state}[k](l, v)
    panda.configure(cfg)
    panda.set_shutter = set_shutter

def table_warmup():
    return dict(
        [("trigger", ["Immediate"])] +
        [(k, [1]) for k in ["repeats", "time1", "time2", "outa1"]] +
        [(k, [0]) for k in ["position"] + seq_outs_not(["outa1"])]
    )

def seq_warmup(block):
    return {
        "pcap.enable": "ONE", "%s.repeats" % block: 1,
        "%s.table" % block: table_warmup()
    }

def seq_dwarmup():
    return {
        "pcap.enable": "ONE", "dseq.enable": 1,
        "dseq.tables": [table_warmup(), None]
    }

def table_slave(atime):
    return dict(
        [
            ("trigger", ["BITA=1", "BITA=0"]),
            ("time1", [atime * PANDA_FREQ, 0]),
            ("outa1", [1, 0]), ("outb1", [1, 0])
        ] + [(k, [1, 1]) for k in ["repeats", "time2"]] +
        [(k, [0, 0]) for k in ["position"] + seq_outs_not(["outa1", "outb1"])]
    )

def cfg_merge(cfg1, cfg0):
    for k, v in cfg0.items():
        v.update(cfg1.get(k, {}))
        if v:
            cfg1[k] = v

def map_seqpos(panda, inps, dseq = False):
    inps = [inp.prefix for inp in inps]
    poss, tmp = (inps.copy(), []), ({}, {})
    for pos in "abc":
        inp = panda.get_input("seq1.pos%s" % pos)
        try:
            poss[0].remove(inp)
            tmp[0][inp] = pos
        except ValueError:
            poss[1].append(pos)
    for i, inp in enumerate(poss[0]):
        tmp[0][inp] = tmp[1][inp] = poss[1][i]
    return "".join(tmp[0][inp] for inp in inps).upper(), {
        "seq%c.pos%s.value" % (c, pos): inp
        for c in ("12" if dseq else "1")
        for inp, pos in tmp[1].items()
    }

def auto_velo(motors, step, duty, period = None, atime = None, velocity = None):
    velo, = set(motor.velocity.get() for motor in motors)
    vmax, = set(motor.motor_vmax.get() for motor in motors)
    if len([x for x in [period, atime, velocity] if x is not None]) > 1:
        raise ValueError("conflicting values for period, atime and velocity")
    elif period is not None or atime is not None:
        if atime is not None:
            period = atime / duty
        velocity = step / period
    else:
        if velocity is None:
            velocity = velo
        period = step / velocity
    assert period > 0.0 and velocity > 0.0
    if vmax > 0.0:
        assert velocity <= vmax
        velos = vmax, velocity
    else:
        if velocity > velo:
            velo = velocity
        velos = velo, velocity
    return period, velos

def final_config_base(configs):
    cache = [(dev, {k: getattr(dev, k).get() for k in
        reversed(list(cfg_trans(dev, {k: None for k in keys})))
    }) for dev, keys in reversed(configs)]
    def plan():
        for dev, cfg in cache:
            yield from bps.configure(dev, cfg)
    return plan()

def final_fly_motor(motor):
    return final_config_base([(motor, ["velocity"])])

def fly_reading(devices, name = "flying"):
    return bps.trigger_and_read(devices, name)

def one_fly_step(detectors, step, pos_cache, take_reading = fly_reading):
    return bps.one_nd_step(detectors, step, pos_cache, take_reading)

def make_grid_step(motor, snake, velos):
    idx = [0]
    def one_grid_step(detectors, step, pos_cache, take_reading = fly_reading):
        if velos and (not snake or idx[0] < 2):
            yield from bps.configure(motor, {"velocity": velos[idx[0] % 2]})
        idx[0] += 1
        yield from bps.one_nd_step(detectors, step, pos_cache, take_reading)
    return one_grid_step

def grid_cfg(args, div, pad, snake_axes, pos_cache, velos):
    assert not len(args) % 4
    naxes = len(args) // 4
    div = list(div) if isinstance(div, collections.abc.Iterable) \
        else [div, naxes - 1]
    assert 0 <= div[1] < naxes
    if div[0] > 0 and div[1] == naxes - 1:
        assert div[0] >= args[-1]
        div = [div[0] // args[-1], naxes - 2]
    for i in range(div[1], naxes - 2):
        div[0] *= args[4 * i + 3]
    pnums, div[1] = [], 1
    for i in range(naxes - 1):
        pnums.append(args[4 * i + 3])
        div[1] *= pnums[-1]
    div[0] = div[1] if div[0] < 0 else max(1, div[0])
    pnums.append(2)
    points = div[1] * args[-1]

    lo, hi = args[-3 : -1]
    pad = -pad if lo > hi else pad
    snake = args[-4] in norm_snake(snake_axes, motors_get(args))
    scans = plans.grid_scan(
        [], *(args[:-3] + (lo - pad, hi + pad, 2)),
        snake_axes = snake_axes, pos_cache = pos_cache, frag = True,
        per_step = make_grid_step(args[-4], snake, velos)
    )
    def scan_gen(steps):
        for i in range(steps):
            yield from next(scans)
    return snake, div, scan_gen, \
        {"num_points": points, "hints": {"progress": ["simple"] + pnums}}

def seq_grid(inp, pos, lo, hi, num, duty, period, pre, snake):
    live, dead = duty * period * PANDA_FREQ, (1.0 - duty) * period * PANDA_FREQ
    assert live >= 1.0 and dead >= 1.0
    step = (hi - lo) / (num - 1)
    pre = pre if step > 0.0 else -pre
    xs = lo - pre, lo - step * duty / 2, hi + pre, hi + step * duty / 2
    scale, offset = inp.scale.get(), inp.offset.get()
    table = dict([
        ("repeats", [1, num, 1, num]),
        ("trigger", ["POS%s%s=POSITION" % (pos, op)
            for op in ("<>><" if step / scale > 0.0 else "><<>")]),
        ("position", [(x - offset) / scale for x in xs]),
        ("time1", [0, live, 0, live]), ("time2", [1, dead, 1, dead]),
        ("outa1", [0, 1, 0, 1]), ("outb1", [0, 1, 0, 1])
    ] + [(k, [0] * 4) for k in seq_outs_not(["outa1", "outb1"])])
    if not snake:
        table = dict((k, [v[0], v[1]]) for k, v in table.items())
    return {"seq1.repeats": 0, "seq1.table": table}

def table_pgrid(inp, pos, lo, hi, num, duty, period, pre, snake):
    units, live = num + duty - 1.0, duty * period * PANDA_FREQ
    assert live >= 1.0 and (1.0 - duty) * period * PANDA_FREQ >= 1.0
    step = (hi - lo) / (num - 1)
    pre = pre if step > 0.0 else -pre
    xs = [lo - pre], [hi + pre]
    lo, hi = lo - step * duty / 2, hi + step * duty / 2
    xs = xs[0] + [((units - i) * lo + i * hi) / units for i in range(num)] + \
        xs[1] + [(i * lo + (units - i) * hi) / units for i in range(num)]
    scale, offset = inp.scale.get(), inp.offset.get()
    pattern = lambda l: [l[0]] + [l[1]] * num + [l[2]] + [l[3]] * num
    table = dict([
        ("repeats", pattern([1] * 4)),
        ("trigger", pattern(["POS%s%s=POSITION" % (pos, op)
            for op in ("<>><" if step / scale > 0.0 else "><<>")])),
        ("position", [(x - offset) / scale for x in xs]),
        ("time1", pattern([0, live, 0, live])), ("time2", pattern([1] * 4)),
        ("outa1", pattern([0, 1, 0, 1])), ("outb1", pattern([0, 1, 0, 1]))
    ] + [(k, pattern([0] * 4)) for k in seq_outs_not(["outa1", "outb1"])])
    if not snake:
        table = dict((k, v[:num + 1]) for k, v in table.items())
    return table

def auto_spad(pad, pad0):
    if pad is None:
        pad = max(pad0)
    else:
        assert pad >= pad0[1]
    return pad

def grid_frag_base(seqs, num, snake, div, scan_gen):
    def points_gen():
        rev = 0
        yield seqs[3], seqs[3], 0, 1
        frag = min(div[0], div[1])
        yield seqs[rev], seqs[2], frag * num, frag * 2 - 1
        while True:
            div[1] -= frag
            if not div[1]:
                break
            if snake:
                rev = (div[0] % 2) - rev
            frag = min(div[0], div[1])
            yield seqs[rev], seqs[2], frag * num, frag * 2
    def frag_gen():
        for mseq, sseq, points, steps in points_gen():
            yield mseq, sseq, {"num_points": points}, scan_gen(steps)
    return frag_gen()

def grid_frag(panda, pos, *args, pcomp, duty = 0.5, div = -1, snake_axes = True,
    period = None, atime = None, velocity = None, pad = None, pos_cache = None):
    motor, lo, hi, num = args[-4:]
    assert num > 1
    step = abs(hi - lo) / (num - 1)
    period, velos = auto_velo([motor], step, duty,
        period = period, atime = atime, velocity = velocity)
    pre = step * duty / 2
    pad = pre + auto_spad(pad, (step * (1.0 - duty / 2),
        velos[1] * motor.acceleration.get() / 2))
    snake, div, scan_gen, md = grid_cfg\
        (args, div, pad, snake_axes, pos_cache, velos)
    if pcomp:
        seqs = [table_pgrid(panda.motors[motor], pos, l, h, num, duty, period,
            (pre + pad) / 2, snake) for l, h in [(lo, hi), (hi, lo)]]
        seqs += [table_slave(duty * period), None]
    else:
        seqs = [seq_grid(panda.motors[motor], pos, l, h, num, duty, period,
            (pre + pad) / 2, snake) for l, h in [(lo, hi), (hi, lo)]]
        seqs += [{"seq1.repeats": 0, "seq1.table": table_slave(duty * period)},
            seq_disable("seq1")]
    return grid_frag_base(seqs, num, snake, div, scan_gen), md

def fly_frag(pandas, devs, frag_gen, fwraps = [], finals = [], md = None):
    if callable(fwraps):
        fwraps = [fwraps]
    @bpp.stage_run_decorator(list(pandas) +
        [panda.ad for panda in pandas] + devs, md = md)
    def inner():
        for mseq, sseq, kwargs, scan in frag_gen:
            def plan():
                for i, panda in enumerate(pandas):
                    yield from bps.configure(panda, sseq if i else mseq)
                for panda in reversed(pandas):
                    yield from bps.configure\
                        (panda.ad, {"cam.acquire": 1}, action = True)
                yield from scan
                for panda in pandas:
                    yield from bps.configure\
                        (panda.ad, {"cam.acquire": 0}, action = True)
            plan = plan()
            for fwrap in fwraps:
                plan = fwrap(plan, **kwargs)
            yield from plan
        for plan in finals:
            yield from plan
    return inner()

def fly_dfrag(pandas, devs, frag_gen, fwraps = [], finals = [], md = None):
    if callable(fwraps):
        fwraps = [fwraps]
    @bpp.stage_run_decorator(list(pandas) +
        [panda.ad for panda in pandas] + devs, md = md)
    def inner():
        for mtabs, stabs, kwargs, scan in frag_gen:
            def plan():
                for i, panda in enumerate(pandas):
                    yield from bps.configure(panda, {
                        "dseq.enable": 1,
                        "dseq.tables": (stabs if i else mtabs) + [None]
                    }, action = True)
                for panda in reversed(pandas):
                    yield from bps.configure\
                        (panda, {"dseq.acquire": 1}, action = True)
                yield from scan
                for panda in pandas:
                    yield from bps.configure(panda, {
                        "dseq.acquire": 0, "dseq.enable": 0
                    }, action = True)
            plan = plan()
            for fwrap in fwraps:
                plan = fwrap(plan, **kwargs)
            yield from plan
        for plan in finals:
            yield from plan
    return inner()

def fwrap_first(plan):
    first = [True]
    def fwrap(scan, **kwargs):
        if first[0]:
            yield from plan
            first[0] = False
        yield from scan
    return fwrap

def fwrap_second(plan):
    second = [True]
    def fwrap(scan, **kwargs):
        yield from scan
        if second[0]:
            yield from plan
            second[0] = False
    return fwrap

def fwrap_config(devs, configs):
    def plan():
        for dev in devs:
            cfg = configs.get(dev)
            if cfg:
                yield from bps.configure(dev, cfg)
    return fwrap_first(plan())

def final_config(devs, configs):
    return final_config_base([(dev, list(configs[dev]))
        for dev in devs if dev in configs])

def fwrap_adtrig(ads):
    def fwrap(scan, *, num_points, **kwargs):
        if num_points:
            for ad in ads:
                yield from bps.configure(ad, {"cam.num_images": num_points})
                yield from bps.configure(ad, {"cam.acquire": 1}, action = True)
        yield from scan
        if num_points:
            for ad in ads:
                yield from bps.configure(ad, {"cam.acquire": 0}, action = True)
    return fwrap

def final_adtrig(ads):
    return final_config_base([(ad, ["cam.num_images"]) for ad in ads])

def auto_shut(shutter, pos_cache):
    def fwrap(scan, *, num_points, **kwargs):
        if num_points:
            yield from bps.move_per_step({shutter: 1}, pos_cache)
        yield from scan
        if num_points:
            yield from bps.move_per_step({shutter: 0}, pos_cache)
    return ([shutter], [fwrap]) if shutter else ([], [])

def fly_grid(pandas, dets, *args, shutter = None,
    configs = {}, md = None, pos_cache = None, **kwargs):
    motors, pos_cache = motors_get(args), norm_cache(pos_cache)
    seqpos = map_seqpos(pandas[0], [pandas[0].motors[motors[-1]]], False)
    shut = auto_shut(shutter, pos_cache)
    frag_gen, _md = grid_frag(pandas[0], seqpos[0], *args,
        pcomp = False, pos_cache = pos_cache, **kwargs)
    devs = list(pandas) + [panda.ad for panda in pandas] + list(dets) + motors
    _md.update(md or {}); cfg_merge(configs, {pandas[0]: seqpos[1]})
    return fly_frag(
        pandas, list(dets) + motors + shut[0], frag_gen,
        shut[1] + [fwrap_adtrig(dets), fwrap_config(devs, configs)],
        [final_adtrig(dets), final_fly_motor(motors[-1]),
            final_config(devs, configs)], md = _md
    )

def fly_dgrid(pandas, dets, *args, shutter = None, pcomp = False,
    configs = {}, md = None, pos_cache = None, **kwargs):
    motors, pos_cache = motors_get(args), norm_cache(pos_cache)
    seqpos = map_seqpos(pandas[0], [pandas[0].motors[motors[-1]]], True)
    shut = auto_shut(shutter, pos_cache)
    frag_gen, _md = grid_frag(pandas[0], seqpos[0], *args,
        pcomp = pcomp, pos_cache = pos_cache, **kwargs)
    devs = list(pandas) + [panda.ad for panda in pandas] + list(dets) + motors
    _md.update(md or {}); cfg_merge(configs, {pandas[0]: seqpos[1]})
    max_rows, = set(panda.dseq.max_rows() for panda in pandas)
    def dfrag_gen():
        for mseq, sseq, kwargs, scan in frag_gen:
            if (not mseq if pcomp else mseq["seq1.repeats"]):
                yield [], [], kwargs, scan
            else:
                if pcomp:
                    repeats = args[-1] + 1
                else:
                    mseq, sseq = mseq["seq1.table"], sseq["seq1.table"]
                    repeats = 2
                repeats = kwargs["num_points"] // args[-1] * repeats
                repeats = repeats // len(mseq["trigger"]), \
                    repeats % len(mseq["trigger"])
                yield split_table({
                    k: v * repeats[0] + v[:repeats[1]]
                    for k, v in mseq.items()
                }, max_rows), split_table({
                    k: v * kwargs["num_points"] for k, v in sseq.items()
                }, max_rows), kwargs, scan
    return fly_dfrag(
        pandas, list(dets) + motors + shut[0], dfrag_gen(),
        shut[1] + [fwrap_adtrig(dets), fwrap_config(devs, configs)],
        [final_adtrig(dets), final_fly_motor(motors[-1]),
            final_config(devs, configs)], md = _md
    )

def sseq_base(scomp):
    def seq(bubo):
        while True:
            msg = bubo.get()
            if msg[0] == "exit" or (scomp(msg) and not bubo.record()):
                return
    return seq

def scomp_pcomp(dev, lo, hi, num, pre, snake):
    sign = -1 if hi < lo else 1
    step = abs(hi - lo) / (num - 1)
    state = [-1, 1]
    def pcomp(msg):
        if msg[0] != "input" or msg[1] != dev:
            return False
        if state[0] >= num:
            if snake:
                if sign * (msg[2] - hi) >= pre:
                    state[0], state[1] = num - 1, -1
                return False
            else:
                state[0] = -1
        if state[0] < 0:
            if sign * (lo - msg[2]) >= pre:
                state[0], state[1] = 0, 1
            return False
        if (sign * (msg[2] - lo) - state[0] * step) * state[1] >= 0:
            state[0] += state[1]
            return True
        return False
    return pcomp

def grid_sfrag(bubo, *args, div = -1,
    snake_axes = True, pad = None, pos_cache = None):
    motor, lo, hi, num = args[-4:]
    bubo.inputs.set([motor.readback]).wait()
    assert num > 1
    step = abs(hi - lo) / (num - 1)
    pad = auto_spad(pad, (step,
        motor.velocity.get() * motor.acceleration.get() / 2))
    snake, div, scan_gen, md = grid_cfg\
        (args, div, pad, snake_axes, pos_cache, None)
    seqs = [sseq_base(scomp_pcomp(motor.readback, l, h, num,
        pad / 2, snake)) for l, h in [(lo, hi), (hi, lo)]]
    seqs += [None, sseq_disable]
    return grid_frag_base(seqs, num, snake, div, scan_gen), md

def sfly_frag(bubo, devs, frag_gen, fwraps = [], finals = [], md = None):
    if callable(fwraps):
        fwraps = [fwraps]
    bubo.outputs.set(devs).wait()
    @bpp.stage_run_decorator([bubo] + devs, md = md)
    def inner():
        for seq, kwargs, scan in frag_gen:
            def plan():
                yield from bps.configure(bubo, {"seq": seq}, action = True)
                yield from bps.configure(bubo, {"enable": 1}, action = True)
                yield from scan
                yield from bps.configure(bubo, {"enable": 0}, action = True)
            plan = plan()
            for fwrap in fwraps:
                plan = fwrap(plan, **kwargs)
            yield from plan
        for plan in finals:
            yield from plan
    return inner()

def sfly_grid(bubo, dets, *args, shutter = None,
    configs = {}, md = None, pos_cache = None, **kwargs):
    motors, pos_cache = motors_get(args), norm_cache(pos_cache)
    shut = auto_shut(shutter, pos_cache)
    frag_gen, _md = grid_sfrag(bubo, *args, pos_cache = pos_cache, **kwargs)
    devs = [bubo] + list(dets) + motors
    _md.update(md or {})
    def sfrag_gen():
        for mseq, sseq, kwargs, scan in frag_gen:
            yield mseq, kwargs, scan
    return sfly_frag(
        bubo, list(dets) + motors + shut[0], sfrag_gen(),
        shut[1] + [fwrap_config(devs, configs)],
        [final_config(devs, configs)], md = _md
    )


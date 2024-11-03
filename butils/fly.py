import math
import re
from bluesky import plans
from bluesky import plan_stubs as bps, preprocessors as bpp
from .bubo import sseq_disable
from .panda import seq_disable, seq_outs_not
from .plans import motors_get, norm_snake

PANDA_FREQ, DSEQ_DELAY = int(125e6), 9

def split_table(table, max_rows, atom_rows = 1):
    n = len(table["trigger"])
    m = max_rows // atom_rows * atom_rows
    return [{k: v[i * m : (i + 1) * m] for k, v in table.items()}
        for i in range(math.ceil(n / m))]

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
        mux, out = out if isinstance(out, tuple) else (out, "a")
        cfg.update([(mux, "SEQ1.OUT" + out.upper())])
    panda.configure(cfg)

def prep_dseq(panda, outputs, inputs, pgate = True, **kwargs):
    cfg = panda.dseq.make_cfg()
    cfg.update(cfg_inputs(panda, inputs, dseq = True, **kwargs))
    luts = dict()
    if pgate:
        outputs = [("pcap.gate", "a"), ("pcap.trig", "a")] + outputs
    for out in outputs:
        mux, out = out if isinstance(out, tuple) else (out, "a")
        luts[out] = ord(out) - ord("a") + 1
        cfg.update([(mux, "LUT%d.OUT" % luts[out])])
    for out in luts:
        cfg.update([
            ("lut%d.inpa" % luts[out], "SEQ1.OUT%s" % out.upper()),
            ("lut%d.inpb" % luts[out], "SEQ2.OUT%s" % out.upper()),
            ("lut%d.func" % luts[out], "A|B")
        ])
    panda.configure(cfg)

def table_warmup():
    return dict(
        [("trigger", ["Immediate"])] +
        [(f, [1]) for f in ["repeats", "time1", "time2", "outa1"]] +
        [(f, [0]) for f in ["position"] + seq_outs_not(["outa1"])]
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

def velo_simple(motor, lo, hi, num, duty,
    period = None, atime = None, velocity = None, pad = None):
    velos = motor.velocity.get()
    if len([x for x in [period, atime, velocity] if x is not None]) > 1:
        raise ValueError("conflicting values for period, velocity and atime")
    elif period is not None or atime is not None:
        if atime is not None:
            period = atime / duty
        velos = velos, abs(hi - lo) / (num - 1) / period
    else:
        velos = (velos, velos) if velocity is None else (velos, velocity)
        period = abs(hi - lo) / (num - 1) / velos[1]
    if pad is None:
        pad = max(0.5, 2 * motor.acceleration.get()) * velos[1]
    assert num > 1 and period > 0.0 and velos[1] > 0.0 and pad > 0.0
    return period, velos, pad

def seq_simple(inp, lo, hi, num, duty, period, pad, snake):
    live, dead = duty * period * PANDA_FREQ, (1.0 - duty) * period * PANDA_FREQ
    assert live >= 1.0 and dead >= 1.0
    if lo > hi:
        pad *= -1
    scale, offset = inp.scale.get(), inp.offset.get()
    lo, hi, pad = (lo - offset) / scale, (hi - offset) / scale, pad / scale
    pos = [(p, inp.root.get_input("seq1.pos%s" % p)) for p in "abc"]
    pos = [p for p, i in pos if i == inp.prefix][0].upper()
    table = dict([
        ("trigger", ["POS%s%s=POSITION" % (pos, op)
            for op in (">><<" if pad > 0.0 else "<<>>")]),
        ("position", [lo, hi + pad / 2, hi, lo - pad / 2]),
        ("time1", [live, 0, live, 0]), ("time2", [dead, 1, dead, 1]),
        ("repeats", [num, 1, num, 1]), ("outa1", [1, 0, 1, 0])
    ] + [(f, [0] * 4) for f in seq_outs_not(["outa1"])])
    if not snake:
        table = dict((k, [v[0], v[3]]) for k, v in table.items())
    return {"seq1.repeats": 0, "seq1.table": table}

def table_pcomp(inp, lo, hi, num, duty, period, pad, snake):
    units, live = num + duty - 1.0, duty * period * PANDA_FREQ
    assert live >= 1.0 and (1.0 - duty) * period * PANDA_FREQ >= 1.0
    if lo > hi:
        pad *= -1
    scale, offset = inp.scale.get(), inp.offset.get()
    pos = [(p, inp.root.get_input("seq1.pos%s" % p)) for p in "abc"]
    pos = [p for p, i in pos if i == inp.prefix][0].upper()
    poss = [((units - x) * lo + x * hi) / units for x in range(num)], \
        [(x * lo + (units - x) * hi) / units for x in range(num)]
    poss = [(x - offset) / scale for x in poss[0] + [hi + pad / 2]] + \
        [(x - offset) / scale for x in poss[1] + [lo - pad / 2]]
    pattern = lambda l: [l[0]] * num + [l[1]] + [l[2]] * num + [l[3]]
    table = dict([
        ("trigger", pattern(["POS%s%s=POSITION" % (pos, op)
            for op in (">><<" if pad > 0.0 else "<<>>")])),
        ("position", poss), ("outa1", pattern([1, 0, 1, 0])),
        ("time1", pattern([live, 0, live, 0])),
        ("time2", pattern([1] * 4)), ("repeats", pattern([1] * 4))
    ] + [(f, pattern([0] * 4)) for f in seq_outs_not(["outa1"])])
    if not snake:
        table = dict((k, v[:num] + v[-1:]) for k, v in table.items())
    return table

def final_config_base(configs):
    cache = [(dev, {k: getattr(dev, k).get() for k in reversed(keys)})
        for dev, keys in reversed(configs)]
    def plan():
        for dev, cfg in cache:
            yield from bps.configure(dev, cfg)
    return plan()

def final_fly_motor(motor):
    return final_config_base([(motor, ["velocity"])])

def make_fly_step(motor, snake, velos, name = "flying"):
    idx = [0]
    def one_fly_step(detectors, step, pos_cache, take_reading =
        lambda devices: bps.trigger_and_read(devices, name = name)):
        if velos and (not snake or idx[0] < 2):
            yield from bps.configure(motor, {"velocity": velos[idx[0] % 2]})
        idx[0] += 1
        yield from bps.one_nd_step(detectors, step,
            pos_cache, take_reading = take_reading)
    return one_fly_step

def grid_cfg(args, div, pad, snake_axes, pos_cache, velos):
    assert not len(args) % 4
    oaxes = len(args) // 4 - 1
    div = [div, oaxes - 1] if isinstance(div, int) else list(div)
    if oaxes:
        assert div[0] >= 0 and 0 <= div[1] < oaxes
        for i in range(div[1], oaxes - 1):
            div[0] *= args[4 * i + 3]
    pnums, div[1] = [], 1
    for i in range(oaxes):
        pnums.append(args[4 * i + 3])
        div[1] *= pnums[-1]
    if not div[0]:
        div[0] = div[1]
    pnums.append(2)
    points = div[1] * args[-1]

    lo, hi = args[-3 : -1]
    pad1 = -pad if lo > hi else pad
    snake = args[-4] in norm_snake(snake_axes, motors_get(args))
    scans = plans.grid_scan(
        [], *(args[:-3] + (lo - pad1, hi + pad1, 2)),
        snake_axes = snake_axes, pos_cache = pos_cache, frag = True,
        per_step = make_fly_step(args[-4], snake, velos)
    )
    def scan_gen(steps):
        for i in range(steps):
            yield from next(scans)
    return snake, div, scan_gen, \
        {"num_points": points, "hints": {"progress": ["simple"] + pnums}}

def grid_frag(seqs, num, snake, div, scan_gen):
    def points_gen():
        rev = 0
        yield seqs[2], 0, 1
        frag = min(div[0], div[1])
        yield seqs[rev], frag * num, frag * 2 - 1
        while True:
            div[1] -= frag
            if not div[1]:
                break
            if snake:
                rev = (div[0] % 2) - rev
            frag = min(div[0], div[1])
            yield seqs[rev], frag * num, frag * 2
    def frag_gen():
        for seq, points, steps in points_gen():
            yield seq, {"num_points": points}, scan_gen(steps)
    return frag_gen()

def frag_simple(panda, *args, pcomp, duty, div = 0, snake_axes = True,
    period = None, atime = None, velocity = None, pad = None, pos_cache = None):
    motor, lo, hi, num = args[-4:]
    period, velos, pad = velo_simple(motor, lo, hi, num, duty,
        period = period, atime = atime, velocity = velocity, pad = pad)
    pad0 = (hi - lo) / (num - 1) * duty / 2
    snake, div, scan_gen, md = grid_cfg\
        (args, div, abs(pad0) + pad, snake_axes, pos_cache, velos)
    lo, hi = lo - pad0, hi + pad0
    if pcomp:
        seqs = [table_pcomp(panda.motors[motor], l, h, num,
            duty, period, pad, snake) for l, h in [(lo, hi), (hi, lo)]]
        seqs.append(None)
    else:
        seqs = [seq_simple(panda.motors[motor], l, h, num,
            duty, period, pad, snake) for l, h in [(lo, hi), (hi, lo)]]
        seqs.append(seq_disable("seq1"))
    return grid_frag(seqs, num, snake, div, scan_gen), md

def fly_frag(panda, adp, devs, frag_gen, fwraps = [], finals = [], md = None):
    if callable(fwraps):
        fwraps = [fwraps]
    @bpp.stage_run_decorator([adp] + devs, md = md)
    def inner():
        yield from bps.configure(panda, {"pcap.enable": "ONE"})
        for seq, kwargs, scan in frag_gen:
            def plan():
                yield from bps.configure(panda, seq)
                yield from bps.configure(adp, {"cam.acquire": 1}, action = True)
                yield from scan
                yield from bps.configure(adp, {"cam.acquire": 0}, action = True)
            plan = plan()
            for fwrap in fwraps:
                plan = fwrap(plan, **kwargs)
            yield from plan
        for plan in finals:
            yield from plan
        yield from bps.configure(panda, {"pcap.enable": "ZERO"})
    return inner()

def fly_dfrag(panda, adp, devs, frag_gen, fwraps = [], finals = [], md = None):
    if callable(fwraps):
        fwraps = [fwraps]
    @bpp.stage_run_decorator([adp] + devs, md = md)
    def inner():
        yield from bps.configure\
            (panda, {"dseq.enable": 0, "pcap.enable": "ONE"})
        for tables, kwargs, scan in frag_gen:
            def plan():
                yield from bps.configure(panda, {
                    "dseq.enable": 1, "dseq.tables": tables + [None]
                }, action = True)
                yield from bps.configure(adp, {"cam.acquire": 1}, action = True)
                yield from bps.configure(panda, {"dseq.poll": 1}, action = True)
                yield from scan
                yield from bps.configure(adp, {"cam.acquire": 0}, action = True)
                yield from bps.configure(panda, {"dseq.enable": 0})
            plan = plan()
            for fwrap in fwraps:
                plan = fwrap(plan, **kwargs)
            yield from plan
        for plan in finals:
            yield from plan
        yield from bps.configure(panda, {"pcap.enable": "ZERO"})
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

def fly_simple(panda, adp, dets, *args,
    configs = {}, md = None, pos_cache = None, **kwargs):
    frag_gen, _md = frag_simple(panda, *args,
        pcomp = False, pos_cache = pos_cache, **kwargs)
    motors = motors_get(args)
    _md.update(md or {})
    return fly_frag(
        panda, adp, list(dets) + motors, frag_gen,
        [fwrap_adtrig(dets), fwrap_config(dets, configs)],
        [final_fly_motor(motors[-1]), final_adtrig(dets),
            final_config(dets, configs)], md = _md
    )

def fly_dseq_simple(panda, adp, dets, *args, pcomp,
    configs = {}, md = None, pos_cache = None, **kwargs):
    frag_gen, _md = frag_simple(panda, *args,
        pcomp = pcomp, pos_cache = pos_cache, **kwargs)
    motors = motors_get(args)
    _md.update(md or {})
    def dfrag_gen():
        for seq, kwargs, scan in frag_gen:
            if (not seq if pcomp else seq["seq1.repeats"]):
                yield [], kwargs, scan
            else:
                if pcomp:
                    repeats = args[-1] + 1
                else:
                    seq, repeats = seq["seq1.table"], 2
                repeats = kwargs["num_points"] // args[-1] * repeats, \
                    len(seq["trigger"])
                repeats = repeats[0] // repeats[1], repeats[0] % repeats[1]
                yield split_table({
                    k: v * repeats[0] + v[:repeats[1]]
                    for k, v in seq.items()
                }, panda.dseq.max_rows()), kwargs, scan
    return fly_dfrag(
        panda, adp, list(dets) + motors, dfrag_gen(),
        [fwrap_adtrig(dets), fwrap_config(dets, configs)],
        [final_fly_motor(motors[-1]), final_adtrig(dets),
            final_config(dets, configs)], md = _md
    )

def fly_dsimple(panda, adp, dets, *args,
    configs = {}, md = None, pos_cache = None, **kwargs):
    return fly_dseq_simple(panda, adp, dets, *args, pcomp = False,
        configs = configs, md = md, pos_cache = pos_cache, **kwargs)

def fly_pcomp(panda, adp, dets, *args,
    configs = {}, md = None, pos_cache = None, **kwargs):
    return fly_dseq_simple(panda, adp, dets, *args, pcomp = True,
        configs = configs, md = md, pos_cache = pos_cache, **kwargs)

def sseq_base(scomp):
    def seq(bubo):
        while True:
            msg = bubo.get()
            if msg[0] == "exit" or (scomp(msg) and not bubo.record()):
                return
    return seq

def scomp_pcomp(dev, lo, hi, num, pad, snake):
    assert num > 1 and pad >= 0.0
    sign = -1 if hi < lo else 1
    step = abs(hi - lo) / (num - 1)
    state = [0, 1]
    def pcomp(msg):
        if msg[0] != "input" or msg[1] != dev:
            return False
        if state[0] >= num:
            if snake:
                if sign * (msg[2] - hi) >= pad / 2:
                    state[0], state[1] = num - 1, -1
                return False
            else:
                state[0] = -1
        if state[0] < 0:
            if sign * (lo - msg[2]) >= pad / 2:
                state[0], state[1] = 0, 1
            return False
        if (sign * (msg[2] - lo) - state[0] * step) * state[1] >= 0:
            state[0] += state[1]
            return True
        return False
    return pcomp

def sfrag_simple(bubo, *args, div = 0,
    snake_axes = True, pad = None, pos_cache = None):
    motor, lo, hi, num = args[-4:]
    bubo.inputs.set([motor.readback]).wait()
    if pad is None:
        pad = max(0.5, 2 * motor.acceleration.get()) * motor.velocity.get()
    snake, div, scan_gen, md = grid_cfg\
        (args, div, pad, snake_axes, pos_cache, None)
    seqs = [sseq_base(scomp_pcomp(motor.readback, l, h, num, pad, snake))
        for l, h in [(lo, hi), (hi, lo)]]
    seqs.append(sseq_disable)
    return grid_frag(seqs, num, snake, div, scan_gen), md

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

def sfly_simple(bubo, dets, *args, md = None, pos_cache = None, **kwargs):
    frag_gen, _md = sfrag_simple(bubo, *args, pos_cache = pos_cache, **kwargs)
    _md.update(md or {})
    return sfly_frag(bubo, list(dets) + motors_get(args), frag_gen, md = _md)


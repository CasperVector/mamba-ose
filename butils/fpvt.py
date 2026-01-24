import bisect
import collections
import numpy
from .fly import PANDA_FREQ, auto_spad, seq_outs_not, split_table, table_slave
try:
    from scipy.special import wrightomega
except ImportError:
    pass

def profile_pad(velo, accl, teps):
    accl = min(accl, velo / teps / 2.02)
    ts = [0.0, teps, velo / accl - teps, velo / accl]
    xs = [0.0, teps ** 2 * accl / 2, 0.0, velo ** 2 / accl / 2]
    xs[2] = xs[3] + xs[1] - teps * velo
    return {"T": numpy.array(ts), "X": numpy.array(xs)}

def auto_tpad(pad, velo, spad):
    pad["X"] -= spad
    return pad, pad["T"][-1] - pad["X"][-1] / velo

def profile_seg(step, velo, accl, teps):
    accl = min(accl, velo / teps / 2.02)
    assert step > 4 * accl * teps ** 2
    ts, xs = [0.0, teps], [0.0, teps ** 2 * accl / 2]
    tacc = velo / accl; sacc = tacc * velo
    if step > sacc:
        thalf = tacc + (step - sacc) / velo / 2
        ts += [tacc - teps, tacc]
        xs += [sacc / 2 + xs[1] - teps * velo, sacc / 2]
    else:
        thalf = numpy.sqrt(step / accl)
        ts += [thalf - teps]
        xs += [step / 2 + xs[1] - teps * thalf * accl]
    ts, xs = numpy.array(ts), numpy.array(xs)
    return {"T": numpy.concatenate((ts, thalf * 2 - ts[::-1])),
        "X": numpy.concatenate((xs, step - xs[::-1]))}

def ptrig_unit(period, atom, duty):
    ticks = period * PANDA_FREQ
    ticks = duty / (2 * atom - 1) * ticks, (1.0 - duty) * ticks
    assert ticks[0] >= 1.0 and ticks[1] >= 1.0
    unit = dict([
        ("repeats", [atom - 1, 1]), ("trigger", ["Immediate", "Immediate"]),
        ("time1", [ticks[0], ticks[0]]), ("time2", [ticks[0], ticks[1]]),
        ("outa1", [1, 1]), ("outb1", [1, 1]), ("outb2", [1, 0]),
    ] + [(k, [0, 0]) for k in
        ["position"] + seq_outs_not(["outa1", "outb1", "outb2"])])
    if atom < 2:
        unit = {k: v[1:] for k, v in unit.items()}
    slave = {k: v + ["BITA=0" if k == "trigger" else
        int(k in ["repeats", "time2"])] for k, v in unit.items()}
    slave["trigger"][0], slave["time2"][-2] = "BITA=1", 1
    pattern = lambda k: (lambda l: lambda n: n * l)(unit[k])
    trigger, position = pattern("trigger"), pattern("position")
    if atom > 2:
        trigger = (lambda p: lambda n, s:
            ["Immediate", s, "Immediate"] + p(n)[1:])(trigger)
        position = (lambda p: lambda n, x: [0, x, 0] + p(n)[1:])(position)
        m = 2
    else:
        trigger = (lambda p: lambda n, s: [s] + p(n)[1:])(trigger)
        position = (lambda p: lambda n, x: [x] + p(n)[1:])(position)
        m = 0
    trig = dict([
        ("repeats", [1, 1, atom - 2][:m + 1]),
        ("time1", [0, ticks[0]][:m]), ("time2", [1, ticks[0]][:m]),
        ("outa1", [0, 1][:m]), ("outb1", [0, 1][:m]), ("outb2", [0, 1][:m]),
    ] + [(k, m * [0]) for k in seq_outs_not(["outa1", "outb1", "outb2"])])
    return dict([
        ("trigger", trigger), ("position", position),
        ("repeats", (lambda p, v: lambda n: v + p(n)[1:])\
            (pattern("repeats"), trig["repeats"])),
    ] + [
        (k, (lambda p, v: lambda n: v + p(n))(pattern(k), trig[k]))
        for k in ["time1", "time2"] + seq_outs_not([])
    ]), unit, slave

def auto_stab(unit, mtab):
    return mtab, dict([(k, mtab["num_points"] * v) for k, v in unit[2].items()])

def ptrig_cond(xs, vs, inps, poss):
    offsets = numpy.array([inp.offset.get() for inp in inps])
    scales = numpy.array([inp.scale.get() for inp in inps])
    pos0, sign0 = numpy.array(list(poss)), numpy.array(list("><"))
    idx0, idx1 = numpy.arange(vs.shape[0]), numpy.abs(vs).argmax(1)
    sign1 = sign0[((vs / scales)[idx0, idx1] < 0.0).astype("int")]
    return ["POS%s%s=POSITION" % (p, s) for p, s in zip(pos0[idx1], sign1)], \
        (xs[idx0, idx1] - offsets[idx1]) / scales[idx1]

archim_t2s = lambda t: 1 / (4 * numpy.pi) * \
    (t * numpy.sqrt(1 + t ** 2) + numpy.arcsinh(t))
# <https://math.stackexchange.com/questions/81636/_/81657>.
archim_s2t = lambda s: numpy.sqrt\
    (numpy.real(wrightomega(8 * numpy.pi * s - numpy.log(2) - 1)) / 2)
# The curvature at a given angle.
archim_t2c = lambda t: (2 * numpy.pi) * (t ** 2 + 2) / (t ** 2 + 1) ** (3 / 2)

def archim_txs(num, sign, tilt, st0, step, origin, smooth, trig):
    assert smooth[0] >= 1 and smooth[1] >= 1
    idx, n0 = [st0[0]], smooth[1] / archim_t2c(archim_s2t(st0[0]))
    while True:
        n = n0 * archim_t2c(archim_s2t(idx[-1]))
        if n <= 1.0:
            break
        idx.append(idx[-1] + 1 / (n * smooth[0]))
    idx = numpy.array(idx)
    idx = idx[idx <= num] if num <= idx[-1] else numpy.concatenate((
        idx, idx[-1] + 1 / smooth[0] * (1 + numpy.arange(
            numpy.ceil((num + st0[0] - idx[-1]) * smooth[0])))
    ))
    ts0 = archim_s2t(idx)
    rs, ts = ts0 / (2 * numpy.pi), (ts0 - st0[1]) * sign + tilt
    xs, ys = rs * numpy.cos(ts), rs * numpy.sin(ts)
    ret = {"T": idx, "X":
        numpy.array((ys * step + origin[1], xs * step + origin[0])).T}
    if trig:
        ret["V"] = numpy.array((
            numpy.sin(ts) / ts0 + sign * numpy.cos(ts),
            numpy.cos(ts) / ts0 - sign * numpy.sin(ts),
        )).T
    return ret

def archim_traj(rad, step, origin = (0.0, 0.0),
    tilt = -numpy.pi / 2, smooth = (1, 1)):
    sign = -1 if rad < 0.0 else 1
    rad = abs(rad); assert rad >= step > 0.0
    s0 = 1 / 2; t0 = archim_s2t(s0)
    num = numpy.ceil(archim_t2s(2 * numpy.pi * (rad / step) - t0))
    traj = archim_txs(num, sign, tilt, (s0, t0), step, origin, smooth, False)
    return (traj, archim_txs(num - 1, sign, tilt, (s0, t0), step, origin,
        (1, 1), True)) if smooth[0] > 1 or smooth[1] > 1 else traj["X"]

def archim_frag(rad, step, origin, tilt, period, accl, spad, teps, div):
    # archim_t2c(archim_s2t(1 / 2)) = 3.32 and a = v ** 2 / r; this also
    # leads to the 6.64 in the following auto_spad() call.
    velo, accl0 = step / period, 3.32 * step / period ** 2
    assert period >= 0.0 and (accl <= 0.0 or accl >= accl0)
    pad = profile_pad(velo, accl0, teps)
    spad = auto_spad(spad, (step / 2, step / 6.64))
    pad, tpad = auto_tpad(pad, velo, spad)
    pad["X"] *= period / step
    pad["X"] = numpy.array((pad["X"], pad["X"])).T
    _traj, _trig = archim_traj(rad, step, origin, tilt, (3, 4))
    _traj["T"] *= period; _trig["T"] *= period
    # archim_t2c(archim_s2t(1.55)) = numpy.pi / 2, where the perimeter
    # of the osculating circle is 4.
    tm, div = 1.55 * period, list(div)
    div[0] = _trig["T"].shape[0] if div[0] < 0 else max(1, div[0])
    div[1] = div[0] if div[1] < 0 else max(1, div[1])
    traj, trig = [], split_table(_trig, div[0])
    for i, tg in enumerate(trig):
        if i + 1 >= len(trig):
            traj.append(_traj)
            continue
        n = bisect.bisect_right(_traj["T"], trig[i + 1]["T"][0])
        traj.append({k: v.copy() for k, v in
            split_table(_traj, n + 1, max_split = 1)[0].items()})
        _traj = split_table(_traj, n - 1, max_split = 1)[1]
    for i, tj in enumerate(traj):
        ts, xs = tj["T"], tj["X"]
        rs = (xs[1] - xs[0]) / (ts[1] - ts[0]), \
            (xs[-1] - xs[-2]) / (ts[-1] - ts[-2])
        traj[i] = {
            "T": numpy.concatenate((pad["T"], tpad - tj["T"][0] + tj["T"],
                2 * tpad - tj["T"][0] + tj["T"][-1] - pad["T"][::-1])),
            "X": numpy.concatenate((xs[0] + rs[0] * pad["X"],
                tj["X"], xs[-1] - rs[1] * pad["X"][::-1])),
        }
    for i, tg in enumerate(trig):
        n = tg["T"].shape[0]
        for l, t in enumerate(tg["T"]):
            if t >= tm:
                break
        else:
            l = n
        idx = list(range(0, l, div[1])), list(range(l, n, div[1]))
        m, idx = len(idx[0]), idx[0] + idx[1]
        tg = trig[i] = {k: tg[k][idx] for k in tg}
        idx = numpy.array(idx + [n])
        tg["T"] += tpad - tg["T"][0]
        tg["N"] = numpy.concatenate((idx[1:] - idx[:-1], [m]))
    return traj, trig

def archim_ptrig(tg, cond, unit):
    ns, m = tg["N"][:-1], tg["N"][-1]
    return auto_stab(unit, dict([
        ("trigger", sum([
            unit[0]["trigger"](n, s) if i < m else
            [s] + (unit[1]["trigger"] * n)[1:]
            for i, (n, s) in enumerate(zip(ns, cond[0]))
        ], [])), ("position", sum([
            unit[0]["position"](n, x) if i < m else
            [x] + (unit[1]["position"] * n)[1:]
            for i, (n, x) in enumerate(zip(ns, cond[1]))
        ], [])), ("time2", sum([
            unit[0]["time2"](n)[:-1] + [1] if i < m else
            (unit[1]["time2"] * n)[:-1] + [1]
            for i, n in enumerate(ns)
        ], [])), ("num_points", ns.sum()),
    ] + [(k, sum([
        unit[0][k](n) if i < m else unit[1][k] * n
        for i, n in enumerate(ns)
    ], [])) for k in ["time1", "repeats"] + seq_outs_not([])]))

def archim_udrift(period, atom, duty, drift):
    return ptrig_unit(period, atom, duty), \
        int((1.0 - duty) / drift) if drift > 0.0 else -1

def snake_lgrid(ls, snake):
    ns = [len(l) for l in ls]
    ret, total = [], numpy.prod(ns)
    for i, (l, s) in enumerate(zip(ls, snake)):
        m = int(numpy.prod(ns[:i])), int(numpy.prod(ns[i + 1:]))
        l = numpy.repeat(l, m[1])
        l = l, numpy.concatenate((l, l[::-1] if s else l))
        ret.append(numpy.concatenate(
            (numpy.tile(l[1], m[0] // 2), numpy.tile(l[0], m[0] % 2))))
    return numpy.array(ret)

def lgrid_xs(*ls, noise, snake = True, seed = None):
    n, ns = len(ls), tuple(len(l) for l in ls)
    if not isinstance(snake, collections.abc.Iterable):
        snake = [snake] * n
    rng = numpy.random.default_rng(seed)
    ret = snake_lgrid(ls, snake).reshape((n,) + ns)
    for i, arg in enumerate(ls):
        if noise[i]:
            ret[i] += noise[i] * rng.uniform(-0.5, 0.5, ns)
    return ret

def grid_xs(*args, noise = 0.0, snake = True, seed = None):
    assert not len(args) % 3
    args = [args[i * 3 : (i + 1) * 3] for i in range(len(args) // 3)]
    n = len(args)
    assert all(arg[0] != arg[1] and arg[2] > 1 for arg in args)
    if not isinstance(noise, collections.abc.Iterable):
        noise = [0.0] * max(0, n - 2) + [noise] * min(2, n)
    assert all(0.0 <= x < 1.0 for x in noise)
    noise = [(arg[1] - arg[0]) / (arg[2] - 1) * x
        for arg, x in zip(args, noise)]
    return lgrid_xs(*[numpy.linspace(*arg) for arg in args],
        noise = noise, snake = snake, seed = seed)

def grid_ramp(ny, dy, arr):
    return numpy.tile(arr, (ny, 1)) + numpy.tile\
        (dy * numpy.arange(ny), (len(arr), 1)).T

def fgrid_prep(y0, y1, ny, x0, x1, nx,
    noise, snake, seed, duty, velo, accl, spad, teps):
    step = abs(x1 - x0) / (nx - 1), abs(y1 - y0) / (ny - 1)
    assert velo[0] > 0.0 and accl > 0.0 and teps > 0.0
    if velo[2] > 0.0:
        period = step[0] / velo[0]
        # The constraint on v_x is needed when an alternation between
        # step * (1 - noise) and step * (1 + noise) moves is executed
        # with trapezoidal acceleration and deceleration; the constraint
        # on v_y can be obtained similarly.
        smax = lambda v: period ** 2 * accl / 4 \
            if period * accl < 2 * v else period * v - v ** 2 / accl
        assert noise * step[1] <= smax(velo[2]) and \
            2 * noise * step[0] <= smax(velo[2] - (1.0 - noise) * velo[0])
    sign = [1, -1][x0 > x1], [1, -1][y0 > y1]
    grid = grid_xs(y0, y1, ny, x0, x1, nx,
        noise = noise, snake = snake, seed = seed)
    grid[1, 0 :: 2] -= sign[0] * step[0] * duty / 2
    grid[1, 1 :: 2] -= sign[0] * step[0] * duty / 2 * (-1 if snake else 1)
    pre = step[0] * noise / 2
    pad = profile_pad(velo[0], accl, teps)
    spad = pre + auto_spad(spad, (step[0] * (1.0 - duty / 2), pad["X"][-1]))
    pad, tpad = auto_tpad(pad, velo[0], spad)
    x0 = x0 - sign[0] * step[0] * duty / 2
    x1 = x1 + sign[0] * step[0] * duty / 2
    tt = step[0] / velo[0] * numpy.arange(nx)
    segx = {"T": tt, "X": min(x0, x1) + step[0] * numpy.arange(nx)}
    segx = {
        "T": numpy.concatenate((pad["T"], tpad + segx["T"],
            2 * tpad + abs(x1 - x0) / velo[0] - pad["T"][::-1])),
        "X": numpy.concatenate((min(x0, x1) + pad["X"],
            segx["X"], max(x0, x1) - pad["X"][::-1])),
    }
    if sign[0] < 0:
        segx["X"] = x0 + x1 - segx["X"]
    segx["X"] = numpy.array(([y0] * segx["T"].shape[0], segx["X"])).T
    if snake:
        segy = profile_seg(step[1] * (1.0 + noise), velo[0], accl, teps)
        segy["X"] = numpy.array((
            y0 + sign[1] * segy["X"] / (1.0 + noise),
            [x1 + sign[0] * spad] * segy["T"].shape[0],
        )).T
        seg = segx, segy, segx.copy(), segy.copy()
        seg[2]["X"] = seg[2]["X"].copy()
        seg[2]["X"][:,1] = x0 + x1 - segx["X"][:,1]
        seg[3]["X"] = seg[3]["X"].copy()
        seg[3]["X"][:,1] = x0 - sign[0] * spad
    else:
        diag = abs(x1 - x0) + 2 * spad, step[1] * (1.0 + noise)
        segy = profile_seg(max(diag), velo[1], accl, teps)
        segy["X"] = numpy.array((
            y0 + sign[1] * step[1] / max(diag) * segy["X"],
            x1 + sign[0] * spad - sign[0] * diag[0] / max(diag) * segy["X"],
        )).T
        seg = segx, segy, segx, segy
    tseg = seg[0]["T"][-1], seg[1]["T"][-1]
    pre = (pre + spad) / 2
    tt = numpy.concatenate(([tpad - pre / velo[0]], tpad + tt))
    tt = numpy.tile(tt, (ny,)) + numpy.repeat\
        ((tseg[0] + tseg[1]) * numpy.arange(ny), nx + 1)
    xs = numpy.tile(x0 - sign[0] * pre, (ny,))
    if snake:
        xs[1 :: 2] = x1 + sign[0] * pre
    xs = numpy.array((y0 + sign[1] * step[1] * numpy.arange(ny), xs))
    xs = numpy.concatenate((xs.reshape((2, -1, 1)), grid), 2)
    return seg, {"T": tt, "S": 2 * tpad + tseg[1],
        "X": xs, "N": [y0, sign[1] * step[1]]}

def fgrid_traj(dy, ny, idx, rev, seg, trig):
    nx, tseg = trig["X"].shape[2] - 1, (seg[0]["T"][-1], seg[1]["T"][-1])
    trig = trig.copy()
    trig["N"] = numpy.array([ny, nx])
    trig["X"] = trig["X"][:, idx : idx + ny]
    if rev:
        seg = seg[2:] + seg[:2]
    tt = numpy.concatenate([(i + 1) // 2 * tseg[0] +
        i // 2 * tseg[1] + s["T"][1:] for i, s in enumerate(seg)])
    xx = numpy.concatenate([s["X"][1:, 1] for i, s in enumerate(seg)])
    yy = numpy.concatenate([i // 2 * dy +
        s["X"][1:, 0] for i, s in enumerate(seg)])
    l = [ny - 1] + [s["T"].shape[0] - 1 for s in seg[:2]]
    l = l[0] // 2, [l[1], 2 * l[1] + l[2]][l[0] % 2]
    ramp = numpy.concatenate((numpy.repeat(
        numpy.arange(l[0]), tt.shape
    ), [l[0]] * l[1]))
    traj = {
        "T": numpy.concatenate((
            seg[0]["T"][:1], 2 * (tseg[0] + tseg[1]) * ramp +
                numpy.concatenate((numpy.tile(tt, l[0]), tt[:l[1]]))
        )), "X": numpy.array((
            idx * dy + numpy.concatenate((
                seg[0]["X"][:1, 0], 2 * dy * ramp +
                    numpy.concatenate((numpy.tile(yy, l[0]), yy[:l[1]]))
            )), numpy.concatenate((
                seg[0]["X"][:1, 1], numpy.tile(xx, l[0]), xx[:l[1]]
            )),
        )),
    }
    l = [s["T"].shape[0] for s in seg[:2]]
    l += [(l[0] - nx) // 2, l[0] + l[1] - 2]
    ramp = grid_ramp(ny, l[3], l[2] + numpy.arange(nx))
    traj["X"][0, ramp] = trig["X"][0, :, 1:]
    traj["X"][1, ramp] = trig["X"][1, :, 1:]
    traj["X"][0, :l[2]] = trig["X"][0, 0, 1]
    traj["X"][0, -l[2]:] = trig["X"][0, -1, -1]
    scale = (trig["X"][0, 1:, 1] - trig["X"][0, :-1, -1]) / dy
    offset = trig["X"][0, :-1, -1] - scale * trig["X"][0, :-1, 0]
    offset, scale = [numpy.tile(a, (l[3] - nx, 1)).T for a in [offset, scale]]
    ramp = grid_ramp(ny - 1, l[3], l[0] - l[2] + numpy.arange(l[3] - nx))
    traj["X"][0, ramp] = offset + scale * traj["X"][0, ramp]
    traj["X"], trig["X"] = traj["X"].T, trig["X"][1].reshape((-1, 1))
    return traj, trig

def fgrid_cond(xs, inps, poss, snake):
    offset, = [inp.offset.get() for inp in inps]
    scale, = [inp.scale.get() for inp in inps]
    pos, = poss
    xs = (xs[:,0] - offset) / scale
    signs = "<>" if xs[0] < xs[1] else "><"
    signs += signs[::-1] if snake else signs
    return ["POS%s%s=POSITION" % (pos, s) for s in signs], xs

def fgrid_frag(snake, div, seg, trig):
    (y0, dy), ny, nx = trig["N"], trig["X"].shape[1], trig["X"].shape[2] - 1
    d = 2 if snake else 1
    div = list(div)
    if div[0] > 0:
        assert div[0] >= nx
        div[0] //= nx
    else:
        div[0] = ny if div[0] else 1
    if div[1] < 0:
        div[1] = div[0]
    traj, trig = zip(*[fgrid_traj(
        dy, min(div[0], ny - i), i, i % d, seg, trig
    ) for i in range(0, ny, div[0])])
    for tg in trig:
        tg["N"] = numpy.concatenate((tg["N"], [div[1]]))
    return list(traj), list(trig)

def fgrid_ptrig(tg, cond, unit):
    (ny, nx, div), s = tg["N"], tg["S"] * PANDA_FREQ
    div, m = max(1, div), len(unit[1]["repeats"])
    div = div, ny // div, ny % div
    pattern = lambda k, v: div[1] * (m * [v] + div[0] * nx * unit[1][k]) + \
        (m * [v] + div[2] * nx * unit[1][k] if div[2] else [])
    ret = dict([("num_points", ny * nx)] + [(k, pattern(k, int(k == "repeats")))
        for k in ["repeats", "time1"] + seq_outs_not([])])
    us = unit[1]["trigger"], unit[1]["position"]
    if tg["N"][2]:
        div = div + (div[1] + min(1, div[2]), ny % (2 * div[0]))
        trigger = [us[0][0], cond[0][0]][-m:] + [cond[0][1]] + us[0][1:], \
            [us[0][0], cond[0][2]][-m:] + [cond[0][3]] + us[0][1:]
        trigger = trigger[0] + (div[0] * nx - 1) * m * us[0][:1] + \
            trigger[div[0] % 2] + (div[0] * nx - 1) * m * us[0][:1]
        time2 = m * [1] + div[0] * \
            ((nx * unit[1]["time2"])[:-1] + [unit[1]["time2"][-1] + s])
        position = [us[1][0], 1][-m:] + [1] + us[1][1:] + \
            (div[0] * nx - 1) * m * us[1][:1]
        ramp = grid_ramp(div[3], len(position), numpy.where(position)[0])
        position = numpy.array(div[1] * position +
            (position[:(1 + div[2] * nx) * m] if div[2] else []))
        position[ramp] = cond[1][grid_ramp\
            (div[3], div[0] * (nx + 1), numpy.arange(2))]
        ret.update({
            "trigger": ny // (2 * div[0]) * trigger + \
                trigger[:((div[0] + div[4] - 1) // div[0] + div[4] * nx) * m],
            "position": position.tolist(),
            "time2": div[1] * (time2[:-1] + [1]) +
                (time2[:(1 + div[2] * nx) * m - 1] + [1] if div[2] else []),
        })
    else:
        trigger = \
            [us[0][0], cond[0][0]][-m:] + nx * ([cond[0][1]] + us[0][1:]) + \
            [us[0][0], cond[0][2]][-m:] + nx * ([cond[0][3]] + us[0][1:])
        position = [us[1][0], 1][-m:] + nx * ([1] + us[1][1:])
        ramp = grid_ramp(ny, len(position), numpy.where(position)[0])
        position = numpy.array(ny * position)
        position[ramp.flatten()] = cond[1]
        ret.update({
            "trigger": ny // 2 * trigger + trigger[:ny % 2 * (nx + 1) * m],
            "position": position.tolist(),
            "time2": (m * [1] + nx * (unit[1]["time2"][:-1] + [1])) * ny,
        })
    return auto_stab(unit, ret)

def fgrid_udprep(period, atom, duty, drift, y0, y1, ny,
    x0, x1, nx, noise, snake, seed, velo, accl, spad, teps):
    seg, trig = fgrid_prep(y0, y1, ny, x0, x1, nx,
        noise, snake, seed, duty, velo, accl, spad, teps)
    tseg = seg[0]["T"][-1] + seg[1]["T"][-1]
    drift = int((1.0 - duty) / drift * period / tseg) if drift > 0.0 else -1
    return ptrig_unit(period, atom, duty), drift, seg, trig

def farray_traj(xs, period, velo, accl, teps):
    ds = xs[1:] - xs[:-1]; ms = numpy.abs(ds).max(1); dim = ds.shape
    seg = [profile_seg(m, velo, accl, teps) for m in ms]
    tseg = numpy.array([0.0] + [s["T"][-1] for s in seg])
    trig = {
        "T": tseg[:-1].cumsum() + period * numpy.arange(dim[0]),
        "S": tseg[1:] / 2, "X": (xs[1:] + xs[:-1]) / 2, "V": (ds.T / ms).T,
    }
    for i in range(dim[0]):
        seg[i] = {
            "T": trig["T"][i] + seg[i]["T"],
            "X": numpy.tile(xs[i], (seg[i]["T"].shape[0], 1)) + \
                trig["V"][i] * numpy.tile(seg[i]["X"], (dim[1], 1)).T
        }
    seg.append({"T": seg[-1]["T"][-1:] + period, "X": seg[-1]["X"][-1:]})
    trig["T"] += trig["S"]
    return {k: numpy.concatenate([s[k] for s in seg]) for k in seg[0]}, trig

def farray_frag(xs, period, velo, accl, teps, div):
    assert velo > 0.0 and accl > 0.0 and \
        teps > 0.0 and period > 0.0 and xs.shape[0] > 1
    div = list(div)
    div[0] = xs.shape[0] if div[0] < 0 else max(1, div[0])
    traj, trig = [], []
    for i in range(0, xs.shape[0], div[0]):
        x = xs[i - 1 : i + div[0]] if i else \
            numpy.concatenate((xs[1 : 2], xs[:div[0]]))
        tj, tg = farray_traj(x, period, velo, accl, teps)
        ts = tg["T"] + tg["S"] + period
        d = ts[-1] - tg["T"][0] + teps if div[1] < 0.0 else div[1]
        _tg, j = {k: (tg[k] if k in "S" else []) for k in "TSXVN"}, 0
        while j < ts.shape[0]:
            n = max(1, bisect.bisect_right(ts[j:], tg["T"][j] + d))
            for k in "TXV":
                _tg[k].append(tg[k][j])
            _tg["N"].append(n); j += n
        traj.append(tj); trig.append({k: numpy.array(_tg[k]) for k in _tg})
    return traj, trig

def farray_ptrig(tg, cond, period):
    num, ticks = tg["S"].shape[0] + tg["N"].shape[0], tg["S"].copy()
    idx = numpy.concatenate(([0], tg["N"].cumsum()))
    mask = numpy.ones(tg["S"].shape, dtype = "bool"); mask[idx[:-1]] = 0
    ticks[idx[:-1]] = period[0] + ticks[idx[:-1]]
    ticks[mask] = period[0] + period[2] + 2 * ticks[mask]
    ticks = ticks * PANDA_FREQ, period[1] * PANDA_FREQ
    return dict([
        ("trigger", sum([
            [cond[0][i]] + n * ["Immediate"] for i, n in enumerate(tg["N"])
        ], [])), ("position", sum([
            [cond[1][i]] + n * [0] for i, n in enumerate(tg["N"])
        ], [])), ("time1", sum([
            list(ticks[0][idx[i] : idx[i + 1]]) + [0]
            for i in range(tg["N"].shape[0])
        ], [])), ("time2", sum([n * [ticks[1]] + [1] for n in tg["N"]], [])),
        ("outa2", sum([n * [1] + [0] for n in tg["N"]], [])),
        ("outb2", sum([n * [1] + [0] for n in tg["N"]], [])),
        ("repeats", num * [1]), ("num_points", tg["S"].shape[0]),
    ] + [(k, num * [0]) for k in seq_outs_not(["outa2", "outb2"])]), \
    dict([(k, tg["S"].shape[0] * v) for k, v in table_slave(period[1]).items()])

def farray_drift(period, drift, teps):
    assert period[0] >= 0.0 and period[1] > 0.0 and period[2] >= 0.0
    return (period[0] + period[2] + 2 * teps) / drift if drift > 0.0 else -1.0


import numpy
from bluesky import plans, plan_stubs as bps, preprocessors as bpp
from butils.fly import auto_velo
from butils.fpvt import archim_traj, \
    fgrid_cond, fgrid_frag, fgrid_ptrig, fgrid_udprep, grid_xs
from butils.plans import make_sub_step, norm_cache
from butils.traj import PMAC_EPS, auto_accl, auto_atom, \
    auto_axes, auto_fpmac, fly_pmac, fpmac_array

def grid3_snake(args, snake):
    snaking = [1, args[2] % 2] if snake else [0, 0]
    def gen():
        cur = args.copy()
        for i in range(2):
            if snaking[i]:
                args[i * 3], args[i * 3 + 1] = args[i * 3 + 1], args[i * 3]
        return cur
    return gen

def fpmac_grid3_rz(
    pandas, pmac, dets, mx, my, mz, th, r0, r1, nr, z0, z1, nz,
    noise = 0.0, origin = (0.0, 0.0), *, shutter = None, atom = None,
    duty = None, div = (-1, 1e6), pcomp = False, snake_axes = True,
    seed = None, period = None, atime = None, velocity = None,
    acceleration = None, pad = None, configs = {}, md = None, pos_cache = None
):
    atom, duty = auto_atom(atom, duty)
    period, velo = auto_velo([mx, my, mz],
        abs(z1 - z0) / (nz - 1), duty, period, atime, velocity)
    vmax, = set(motor.motor_vmax.get() for motor in [mx, my, mz])
    velo = list(velo[::-1]) + [vmax]
    accl = auto_accl([mx, my, mz], acceleration)
    udprep = fgrid_udprep(period, atom, duty, div[1], r0, r1, nr,
        z0, z1, nz, noise, snake_axes, seed, velo, accl, pad, PMAC_EPS)
    traj, trig = fgrid_frag(snake_axes, (div[0], int(not pcomp)), *udprep[2:])
    for tj in traj:
        rs = tj["X"][:,0]
        tj["X"] = numpy.array((origin[0] + rs * numpy.cos(th),
            origin[1] + rs * numpy.sin(th), tj["X"][:,1])).T
    axes, inps, poss, pcfg = auto_axes(pandas[0], None, [mz], configs)
    axes = "".join(motor.cs_axis.get() for motor in [mx, my, mz]).lower()
    pmac.use_axes(axes)
    cond = [fgrid_cond(tg["X"], inps, poss, snake_axes) for tg in trig]
    trig = [fgrid_ptrig(tg, c, udprep[0]) for tg, c in zip(trig, cond)]
    traj, trig, kwargs, md = auto_fpmac(pandas, traj, trig,
        axes, md, [len(u["repeats"]) for u in udprep[0][1:]])
    return fly_pmac(pandas, pmac, dets, [mx, my, mz], traj, trig, shutter,
        kwargs, configs = configs, md = md, pos_cache = pos_cache)

def fpmac_grid3(
    pandas, pmac, dets, mt, mx, my, mz, t0, t1, nt, r0, r1, nr,
    z0, z1, nz, noise = 0.0, origin = (0.0, 0.0), *, torigin = 0.0,
    shutter = None, snake_axes = True, seed = None, md = None, **kwargs
):
    if not isinstance(seed, numpy.random.Generator):
        seed = numpy.random.default_rng(seed)
    pos_cache = norm_cache(None)
    gen = grid3_snake([r0, r1, nr, z0, z1, nz], snake_axes)
    g = iter(numpy.radians(numpy.linspace(t0, t1, nt) - torigin))
    sub = lambda: fpmac_grid3_rz(
        pandas, pmac, dets, mx, my, mz, next(g), *gen(), noise = noise,
        origin = origin, shutter = shutter, snake_axes = snake_axes,
        seed = seed, pos_cache = pos_cache, **kwargs
    )
    devs = list(pandas) + [panda.ad for panda in pandas] + [pmac] + \
        list(dets) + [mt, mx, my, mz] + ([shutter] if shutter else [])
    _md = {"num_points": nt * nr * nz}; _md.update(md or {})
    return bpp.stage_run_wrapper(bpp.stub_wrapper(plans.grid_scan(
        dets, mt, t0, t1, nt, snake_axes = snake_axes,
        per_step = make_sub_step(sub), pos_cache = pos_cache
    )), devs, md = _md)

def fparams_grid3(*args, **kwargs):
    duty = auto_atom(kwargs.get("atom"), kwargs.get("duty"))[1]
    period = auto_velo(
        list(args[2 : 5]),
        abs(args[12] - args[11]) / (args[13] - 1),
        duty, *[kwargs.get(k) for k in
            ["period", "atime", "velocity"]]
    )[0]
    return duty * period, period

def grid3_xs(t0, t1, nt, r0, r1, nr, z0, z1, nz, noise = 0.0,
    origin = (0.0, 0.0), torigin = 0.0, snake = True, seed = None):
    if not isinstance(seed, numpy.random.Generator):
        seed = numpy.random.default_rng(seed)
    gen = grid3_snake([r0, r1, nr, z0, z1, nz], snake)
    rz = numpy.array([grid_xs(*gen(), noise = noise,
        snake = snake, seed = seed) for i in range(nt)])
    ts = numpy.tile(numpy.linspace(t0, t1, nt), (nz, nr, 1)).T
    rs, theta = rz[:,0], numpy.radians(ts - torigin)
    return numpy.array((ts, origin[0] + rs * numpy.cos(theta),
        origin[1] + rs * numpy.sin(theta), rz[:,1]))

def fpmac_sgrid3(
    pandas, pmac, dets, mt, mx, my, mz, t0, t1, nt, r0, r1, nr,
    z0, z1, nz, noise = 0.0, origin = (0.0, 0.0), *, torigin = 0.0,
    shutter = None, snake_axes = True, seed = None, md = None, **kwargs
):
    pos_cache = norm_cache(None)
    g = iter(grid3_xs(t0, t1, nt, r0, r1, nr, z0, z1, nz, noise, origin,
        torigin, snake_axes, seed).reshape((4, nt, -1))[1:].transpose(1, 2, 0))
    sub = lambda: fpmac_array(pandas, pmac, dets, [mx, my, mz], next(g),
        shutter = shutter, pos_cache = pos_cache, **kwargs)
    devs = list(pandas) + [panda.ad for panda in pandas] + [pmac] + \
        list(dets) + [mt, mx, my, mz] + ([shutter] if shutter else [])
    _md = {"num_points": nt * nr * nz}; _md.update(md or {})
    return bpp.stage_run_wrapper(bpp.stub_wrapper(plans.grid_scan(
        dets, mt, t0, t1, nt, snake_axes = snake_axes,
        per_step = make_sub_step(sub), pos_cache = pos_cache
    )), devs, md = _md)

def shut_wrapper(inner, step0, pos_cache, shutter):
    if not shutter:
        return inner
    def plan():
        if step0 is not None:
            yield from bps.move_per_step({shutter: 0}, pos_cache)
            yield from bps.move_per_step(step0, pos_cache)
        yield from bps.move_per_step({shutter: 1}, pos_cache)
        yield from inner
    return bpp.finalize_wrapper(plan(),
        bps.move_per_step({shutter: 0}, pos_cache))

def step_array(dets, motors, xs, *, shutter = None, md = None):
    pos_cache = norm_cache(None)
    return shut_wrapper(plans.list_scan(
        dets, *sum(zip(motors, xs.T), ()),
        md = md, pos_cache = pos_cache
    ), dict(zip(motors, xs[0])), pos_cache, shutter)

def make_step_plans(step_array, torigin = 0.0):
    def step_archim(dets, m2, m1, rad, step,
        origin = (0.0, 0.0), tilt = -numpy.pi / 2, **kwargs):
        return step_array(dets, [m2, m1], archim_traj\
            (rad, step, origin = origin, tilt = tilt), **kwargs)
    def step_grid(dets, m2, m1, y0, y1, ny, x0, x1, nx,
        noise = 0.0, *, snake_axes = True, seed = None, **kwargs):
        return step_array(dets, [m2, m1], grid_xs(
            y0, y1, ny, x0, x1, nx, noise = noise,
            snake = snake_axes, seed = seed
        ).reshape((2, -1)).T, **kwargs)
    def step_grid3(
        dets, mt, mx, my, mz, t0, t1, nt, r0, r1, nr, z0, z1, nz,
        noise = 0.0, origin = (0.0, 0.0), *, torigin = torigin,
        snake_axes = True, seed = None, **kwargs
    ):
        return step_array(dets, [mt, mx, my, mz], grid3_xs(
            t0, t1, nt, r0, r1, nr, z0, z1, nz,
            noise, origin, torigin, snake_axes, seed
        ).reshape((4, -1)).T, **kwargs)
    return {
        "step_archim": step_archim,
        "step_grid": step_grid, "step_grid3": step_grid3,
    }


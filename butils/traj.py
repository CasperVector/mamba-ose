import numpy
from bluesky import plan_stubs as bps
from bluesky.utils import short_uid
from ophyd import Component, Device, EpicsSignal, EpicsSignalRO, Signal
from ophyd.status import Status
from .fly import auto_delay, auto_shut, auto_velo, \
    cfg_merge, cfg_seqpos, final_adtrig, final_config, \
    fly_dfrag, fwrap_adtrig, fwrap_config, inp_seqpos, split_table
from .fpvt import ptrig_cond, archim_traj, grid_xs, \
    archim_frag, archim_ptrig, archim_udrift, fgrid_cond, fgrid_frag, \
    fgrid_ptrig, fgrid_udprep, farray_frag, farray_ptrig, farray_drift
from .ophyd import MyEpicsMotor
from .plans import norm_cache

PMAC_FREQ, PMAC_EPS = int(1e6), 2e-3

def auto_atom(atom, duty):
    if atom is None:
        atom = 1
    else:
        assert atom > 0
    if duty is None:
        duty = 1.0 - 1.0 / (2 * atom)
    else:
        assert 0.0 < duty < 1.0
    return atom, duty

class PmacMotor(MyEpicsMotor):
    cs_axis = Component(EpicsSignalRO, ":CsAxis_RBV", kind = "omitted")

class PmacBufEnable(Signal):
    def put(self, val):
        if self._readback and not val:
            if self.root._op_states["execute"][0]:
                self.root.do_abort()
        super().put(1 if val else 0)

class PmacBufTables(Signal):
    def put(self, tables):
        root = self.root
        table, nil = tables; assert nil is None
        table = {k: v for k, v in table.items() if not k.startswith("_")}
        assert all(k.endswith("_positions") or
            k in ["time_array"] for k in table)
        n, = set(len(table[k]) for k in table)
        root.num_build.put(n)
        for k in table:
            getattr(root, k).put(table[k])
        root.do_traj("build").wait()
        super().put("")

    def _set_and_wait(self, value, timeout, **kwargs):
        self.put(value)

class PmacTrajBase(Device):
    num_total = Component(EpicsSignal, "ProfileNumPoints", kind = "config")
    num_build = Component(EpicsSignal, "ProfilePointsToBuild_RBV",
        write_pv = "ProfilePointsToBuild", kind = "normal")
    time_array = Component(EpicsSignal, "ProfileTimeArray", kind = "normal")
    cs_name = Component(EpicsSignal, "ProfileCsName_RBV",
        write_pv = "ProfileCsName", string = True, kind = "config")
    buf_enable = Component(PmacBufEnable, value = 0, kind = "config")
    buf_tables = Component(PmacBufTables, value = "", kind = "omitted")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._op_states = {}
        for op in ["build", "append", "execute"]:
            self._op_states[op] = [None,
                getattr(self, op + "_state").subscribe(self._state_cb(op))]

    def use_axes(self, axes):
        for ax in "abcuvwxyz":
            getattr(self, ax + "_use_axis").set(ax in axes.lower()).wait()

    def _state_cb(self, op):
        def cb(*, value, old_value, **kwargs):
            status = self._op_states[op][0]
            if not status:
                return
            if old_value and not value:
                self._op_states[op][0] = None
                status._finished(getattr(self, op + "_status").get() == 1)
        return cb

    def do_traj(self, op):
        self._op_states[op][0] = status = Status(self)
        getattr(self, "profile_" + op).put(1)
        return status

    def do_abort(self):
        getattr(self, self.cs_name.get().lower() + "_abort").put(1)

    def trigger(self):
        return self.do_traj("execute")

    def stage(self):
        super().stage()
        self.buf_enable.set(0).wait()

    def unstage(self):
        self.buf_enable.set(0).wait()
        super().unstage()

def PmacTraj(prefix, *, name, cses = ["CS1"], inherit = None, **kwargs):
    if not inherit:
        inherit = PmacTrajBase,
    return type("PmacTraj", inherit, dict(sum([[
        ("profile_%s" % op.lower(), Component(EpicsSignal,
            "Profile%s" % op, kind = "omitted")),
        ("%s_state" % op.lower(), Component(EpicsSignalRO,
            "Profile%sState_RBV" % op, kind = "omitted", auto_monitor = True)),
        ("%s_status" % op.lower(), Component(EpicsSignalRO,
            "Profile%sStatus_RBV" % op, kind = "omitted")),
    ] for op in ["Build", "Append", "Execute"]], []) + sum([[
        ("%s_use_axis" % ax.lower(), Component(EpicsSignal,
            "%s:UseAxis" % ax, kind = "config")),
        ("%s_positions" % ax.lower(), Component(EpicsSignal,
            "%s:Positions" % ax, kind = "normal")),
    ] for ax in "ABCUVWXYZ"], []) + sum([[
        ("%s_abort" % cs.lower(), Component(EpicsSignal,
            "%s:Abort" % cs, kind = "omitted")),
    ] for cs in cses], [])))(prefix, name = name, **kwargs)

def auto_accl(motors, acceleration):
    if acceleration is not None:
        return acceleration
    accl, = set(motor.velocity.get() / motor.acceleration.get()
        for motor in motors)
    return accl

def auto_axes(panda, pmac, motors, configs):
    axes = "".join(motor.cs_axis.get() for motor in motors).lower()
    inps = [panda.motors[motor] for motor in motors]
    pcfg = cfg_seqpos(panda, motors[-1:], True)
    if pmac:
        pmac.use_axes(axes)
    if configs:
        cfg_merge(configs, pcfg)
    return inps, inp_seqpos(inps), axes, pcfg

def ptraj_time(times, teps = PMAC_EPS, freq = PMAC_FREQ):
    times = times.copy()
    times[1:] -= times[:-1]
    times[0] = teps
    return times * freq

def pmac_traj(tj, axes):
    ret = {"_cs_axes": axes, "time_array": ptraj_time(tj["T"])}
    ret.update([("%s_positions" % ax, xs) for ax, xs in zip(axes, tj["X"].T)])
    return ret

def move_pmac(pmac, tj):
    group = short_uid("trigger")
    yield from bps.configure\
        (pmac, {"buf_enable": 1, "buf_tables": [tj, None]}, action = True)
    yield from bps.trigger(pmac, group = group)
    yield from bps.wait(group = group)
    yield from bps.configure(pmac, {"buf_enable": 0}, action = True)

def fly_pmac(pandas, pmac, dets, motors, traj, trig, shutter,
    kwargs, configs = {}, md = None, pos_cache = None):
    pos_cache = norm_cache(pos_cache)
    shut = auto_shut(shutter, pos_cache)
    devs = list(pandas) + [panda.ad for panda in pandas] + \
        [pmac] + list(dets) + list(motors)
    if pos_cache["super_step"] is None:
        pos_cache["super_step"] = {}
    take_reading = lambda devices: \
        bps.trigger_and_read(devices, name = "flying")
    def frag_gen():
        tj = None
        for tj, (mtab, stab), kw in zip(traj, trig, kwargs):
            pos_cache["super_step"].update(zip(motors,
                [tj["%s_positions" % ax][0] for ax in tj["_cs_axes"]]))
            yield [], [], {"num_points": 0}, bps.one_nd_step\
                ([], {}, pos_cache, take_reading = take_reading)
            yield mtab, stab, kw, move_pmac(pmac, tj)
        if tj:
            pos_cache["super_step"].update(zip(motors,
                [tj["%s_positions" % ax][-1] for ax in tj["_cs_axes"]]))
            yield [], [], {"num_points": 0}, bps.one_nd_step\
                ([], {}, pos_cache, take_reading = take_reading)
    return fly_dfrag(
        pandas, [pmac] + list(dets) + motors + shut[0], frag_gen(),
        shut[1] + [fwrap_adtrig(dets), fwrap_config(devs, configs)],
        [final_adtrig(dets), final_config(devs, configs)], md = md
    )

def auto_fpmac(pandas, traj, trig, axes, md, atom):
    traj = [pmac_traj(tj, axes) for tj in traj]
    points = [mtab.pop("num_points") for mtab, stab in trig]
    mrows, = set(panda.dseq.max_rows() for panda in pandas)
    for i in range(len(trig)):
        trig[i] = [auto_delay(split_table(table, mrows, a))
            for table, a in zip(trig[i], atom)]
    kwargs = [{"num_points": n} for n in points]
    _md = {"num_points": sum(points),
        "hints": {"progress": ["base", [0] + points]}}
    _md.update(md or {})
    return traj, trig, kwargs, _md

def fpmac_archim(
    pandas, pmac, dets, m2, m1, rad, step, offset = (0.0, 0.0),
    tilt = -numpy.pi / 2, *, shutter = None, atom = None, duty = None,
    div = (-1, 1e6), period = None, atime = None, velocity = None,
    acceleration = None, configs = {}, md = None, pos_cache = None
):
    atom, duty = auto_atom(atom, duty)
    period = auto_velo([m2, m1], step, duty, period, atime, velocity)[0]
    accl = auto_accl([m2, m1], acceleration)
    udrift = archim_udrift(period, atom, duty, div[1])
    traj, trig = archim_frag(rad, step, offset, tilt,
        period, accl, PMAC_EPS, (div[0], udrift[1]))
    inps, poss, axes, pcfg = auto_axes(pandas[0], pmac, [m2, m1], configs)
    cond = [ptrig_cond(tg["X"], tg["V"], inps, poss) for tg in trig]
    trig = [archim_ptrig(tg, c, udrift[0]) for tg, c in zip(trig, cond)]
    traj, trig, kwargs, md = auto_fpmac(pandas, traj, trig,
        axes, md, [len(u["repeats"]) for u in udrift[0][1:]])
    return fly_pmac(pandas, pmac, dets, [m2, m1], traj, trig, shutter,
        kwargs, configs = configs, md = md, pos_cache = pos_cache)

def fpmac_grid(
    pandas, pmac, dets, m2, m1, y0, y1, ny, x0, x1, nx, noise = 0.0,
    *, shutter = None, atom = None, duty = None, div = (-1, 1e6),
    pcomp = False, snake_axes = True, seed = None, period = None,
    atime = None, velocity = None, acceleration = None,
    configs = {}, md = None, pos_cache = None
):
    atom, duty = auto_atom(atom, duty)
    period, velo = auto_velo([m2, m1],
        abs(x1 - x0) / (nx - 1), duty, period, atime, velocity)
    vmax, = set(motor.motor_vmax.get() for motor in [m2, m1])
    velo = list(velo[::-1]) + [vmax]
    accl = auto_accl([m2, m1], acceleration)
    udprep = fgrid_udprep(period, atom, duty, div[1], y0, y1, ny,
        x0, x1, nx, noise, snake_axes, seed, velo, accl, PMAC_EPS)
    traj, trig = fgrid_frag(snake_axes, (div[0], int(not pcomp)), *udprep[2:])
    inps, poss, axes, pcfg = auto_axes(pandas[0], None, [m1], configs)
    axes = "".join(motor.cs_axis.get() for motor in [m2, m1]).lower()
    pmac.use_axes(axes)
    cond = [fgrid_cond(tg["X"], inps, poss, snake_axes) for tg in trig]
    trig = [fgrid_ptrig(tg, c, udprep[0]) for tg, c in zip(trig, cond)]
    traj, trig, kwargs, md = auto_fpmac(pandas, traj, trig,
        axes, md, [len(u["repeats"]) for u in udprep[0][1:]])
    return fly_pmac(pandas, pmac, dets, [m2, m1], traj, trig, shutter,
        kwargs, configs = configs, md = md, pos_cache = pos_cache)

def fpmac_array(
    pandas, pmac, dets, motors, xs, *, shutter = None,
    period, div = (-1, 1e6), velocity = None, acceleration = None,
    configs = {}, md = None, pos_cache = None
):
    velo, = set(motor.velocity.get() for motor in motors)
    vmax, = set(motor.motor_vmax.get() for motor in motors)
    if velocity is None:
        velocity = vmax if vmax > 0.0 else velo
    else:
        if vmax > 0.0:
            assert velocity <= vmax
    assert velocity > 0.0
    accl = auto_accl(motors, acceleration)
    drift = farray_drift(period, div[1], PMAC_EPS)
    traj, trig = farray_frag\
        (xs, sum(period), velocity, accl, PMAC_EPS, (div[0], 0.0))
    inps, poss, axes, pcfg = auto_axes(pandas[0], pmac, motors, configs)
    cond = [ptrig_cond(tg["X"], tg["V"], inps, poss) for tg in trig]
    trig = [farray_ptrig(tg, c, period) for tg, c in zip(trig, cond)]
    traj, trig, kwargs, md = auto_fpmac(pandas, traj, trig, axes, md, (1, 2))
    return fly_pmac(pandas, pmac, dets, motors, traj, trig, shutter,
        kwargs, configs = configs, md = md, pos_cache = pos_cache)

def fpmac_list(pandas, pmac, dets, *args, **kwargs):
    motors = [arg[0] for arg in args]
    xs = numpy.array([arg[1:] for arg in args])
    return fpmac_array(pandas, pmac, dets, motors, xs, **kwargs)

def fpmac_sarchim(pandas, pmac, dets, m2, m1, rad, step,
    offset = (0.0, 0.0), tilt = -numpy.pi / 2, **kwargs):
    xs = archim_traj(rad, step, offset = offset, tilt = tilt)
    return fpmac_array(pandas, pmac, dets, [m2, m1], xs, **kwargs)

def fpmac_sgrid(pandas, pmac, dets, m2, m1, y0, y1, ny, x0, x1, nx,
    noise = 0.0, *, snake_axes = True, seed = None, **kwargs):
    xs = grid_xs(y0, y1, ny, x0, x1, nx, noise, snake_axes, seed)
    xs = xs.reshape((2, -1)).T
    return fpmac_array(pandas, pmac, dets, [m2, m1], xs, **kwargs)


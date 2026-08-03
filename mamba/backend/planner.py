import os
from bluesky import plans
from bluesky.callbacks.core import CallbackBase
from butils.data import ImageFiller, my_broker
from butils.fly import auto_velo, fly_sgrid, fly_dgrid, fly_grid, sfly_grid
from butils.plans import motors_get, plan_fmt
from butils.traj import auto_atom, fpmac_archim, fpmac_grid, \
    fpmac_array, fpmac_list, fpmac_sarchim, fpmac_sgrid
from .progress import ProgressReporter, progressBars

class BasePlanner(object):
    plans, U = [], None

    def __init__(self):
        self.plans = {k: getattr(plans, k) for k in self.plans}

    def check(self, plan, *args, **kwargs):
        pass

    def callback(self, plan, *args, **kwargs):
        return [self.U.mzcb]

    def md_gen(self, plan, *args, **kwargs):
        return kwargs["md"]

    def args_gen(self, plan, *args, **kwargs):
        md = self.md_gen(plan, *args,
            md = kwargs.pop("md", None) or {}, **kwargs)
        kwargs["md"] = {"plan_cmd": plan_fmt(("P." + plan, args, kwargs))}
        return plan, args, kwargs, md

    def run(self, plan, *args, **kwargs):
        self.check(plan, *args, **kwargs)
        cb = self.callback(plan, *args, **kwargs)
        plan, args, kwargs, md = self.args_gen(plan, *args, **kwargs)
        return self.U.RE(self.plans[plan](*args, **kwargs), cb, md = md)

class ChildPlanner(BasePlanner):
    parent = None

    def md_gen(self, plan, *args, **kwargs):
        return self.parent.md_gen(plan, *args, **kwargs)

class ParentPlanner(BasePlanner):
    def __init__(self, U):
        super().__init__()
        self.U, self.origins = U, [self]

    def extend(self, child):
        self.origins.append(child)
        child.U, child.parent = self.U, self

    def make_plans(self):
        ret = type("MambaPlans", (object,), {"_plans": {}})()
        for obj in self.origins:
            for plan in obj.plans:
                ret._plans[plan] = obj.plans[plan]
                setattr(ret, plan, (lambda run, plan:
                    lambda *args, **kwargs: run(plan, *args, **kwargs)
                )(obj.run, plan))
        return ret

class MambaPlanner(ParentPlanner):
    plans = ["list_grid_scan", "list_scan", "grid_scan", "scan", "count"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plans["grid_scan"] = lambda *args, snake_axes = True, **kwargs: \
            plans.grid_scan(*args, snake_axes = snake_axes, **kwargs)
        self.progress = ProgressReporter(progressBars, self.U.mzs.notify)

    def callback(self, plan, *args, **kwargs):
        return [self.U.mzcb, self.progress]

    def md_gen(self, plan, *args, **kwargs):
        md = self.U.mdg.read_advance() if hasattr(self.U, "mdg") else {}
        md.update(kwargs["md"])
        return md

class ImagePlanner(MambaPlanner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filler = ImageFiller()

    def callback(self, plan, *args, **kwargs):
        return [self.filler, self.U.mzcb, self.progress]

class DbPlanner(ImagePlanner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = my_broker(os.getcwd())

    def callback(self, plan, *args, **kwargs):
        return [self.db.insert, self.filler, self.U.mzcb, self.progress]

class AttiPlanner(ChildPlanner):
    def __init__(self, atti, motors):
        super().__init__()
        self.atti = atti
        self.plans["atti_scan"] = lambda dets, *args, md = None: plans.scan(
            list(dets) + list(set(motors) - set(args[:-1 : 3])),
            *args, md = md
        )

def div_get(divs, dets):
    div = [divs[det] for det in dets if det in divs]
    return min(div) if div else -1

def encoder_check(panda, tols, motors):
    for motor in motors:
        inp, tol = panda.motors.get(motor), tols.get(motor)
        if inp is None or tol is None:
            continue
        delta = inp.calibrate(False)
        print("%s.motor_rep - %s.value = %.3g EGU" %
            (motor.vname(), inp.vname(), delta))
        if abs(delta) > tol:
            raise RuntimeError(("abs(%.3g) > %.3g; execute `%s.calibrate()'" +
                " and inform beamline operator") % (delta, tol, inp.vname()))

def vbas_check(ratios, args, kwargs):
    motor, lo, hi, num = args[-4:]
    ratio = ratios.get(motor)
    if ratio is None:
        return
    velocity = auto_velo([motor], abs(hi - lo) / (num - 1), kwargs["duty"],
        **{k: kwargs.get(k) for k in ["period", "atime", "velocity"]})[1][1]
    if velocity < ratio * motor.motor_vbas.get():
        raise RuntimeError("%s.velocity < %f * %s.motor_vbas" %
            (motor.vname(), ratio, motor.vname()))

class HDF5Checker(CallbackBase):
    def __init__(self, tols, dets, num):
        self.tols, self.dets, self.num = tols, dets, num

    def start(self, doc):
        self.idx = [0, 0]
        self.names = {}, {}

    def descriptor(self, doc):
        if doc["name"] in self.names[1]:
            self.names[0].pop(self.names[1][doc["name"]])
        self.names[0][doc["uid"]] = doc["name"]
        self.names[1][doc["name"]] = doc["uid"]

    def event(self, doc):
        if self.names[0][doc["descriptor"]] == "primary":
            self.idx[1] += 1
            return
        self.idx[0] += 1
        cur = self.cur_get()
        if cur is None:
            return
        for det in self.dets:
            tol = self.tols.get(det)
            if tol is None:
                continue
            sig = det.hdf1.array_counter
            cnt = sig.get()
            if not (cur - tol <= cnt <= cur):
                raise RuntimeError(("Unexpected value of %s:" +
                    " %d, should be %d") % (sig.vname(), cnt, cur))

    def cur_get(self):
        if self.idx[0] % 2:
            return None
        return self.idx[0] // 2 * self.num + self.idx[1]

class BuboPlanner(ChildPlanner):
    def __init__(self, bubo, *, divs = {}, h5_tols = {}, configs = {}):
        super().__init__()
        self.bubo, self.divs = bubo, divs
        self.h5_tols, self._configs = h5_tols, configs
        self.plans["sfly_grid"] = self.plan_wrap("sfly_grid", sfly_grid)

    def plan_wrap(self, k, f):
        return lambda *args, **kwargs: f(
            self.bubo, *args, div = div_get(self.divs, args[0]),
            configs = self.configs(k, *args, **kwargs), **kwargs
        )

    def configs(self, plan, *args, **kwargs):
        return self._configs.copy()

    def callback(self, plan, *args, **kwargs):
        return [HDF5Checker(self.h5_tols, args[0], args[-1]),
            self.U.mzcb, self.parent.progress]

class PandaPlanner(ChildPlanner):
    configs = BuboPlanner.configs

    def __init__(self, pandas, *, divs = {}, h5_tols = {},
        enc_tols = {}, vbas_ratios = {}, configs = {}):
        super().__init__()
        self.divs, self.h5_tols, self.enc_tols = divs, h5_tols, enc_tols
        self.vbas_ratios, self._configs = vbas_ratios, configs
        self.motors = self.motors_prep(pandas)
        for k, f in [("fly_sgrid", fly_sgrid),
            ("fly_dgrid", fly_dgrid), ("fly_grid", fly_grid)]:
            self.plans[k] = self.plan_wrap(k, f)

    def plan_wrap(self, k, f):
        return lambda *args, **kwargs: f(
            self.motors_map(motors_get(args[1:])[-1:]),
            *args, div = div_get(self.divs, args[0]),
            configs = self.configs(k, *args, **kwargs), **kwargs
        )

    def fly_params(self, plan, *args, **kwargs):
        motor, lo, hi, num = args[-4:]
        period = auto_velo(
            [motor], abs(hi - lo) / (num - 1), kwargs["duty"], **\
            {k: kwargs.get(k) for k in ["period", "atime", "velocity"]}
        )[0]
        return period * kwargs["duty"], period

    def motors_prep(self, pandas):
        motorl = [(m, tuple(ps)) for ps in pandas for m in ps[0].motors]
        motord = dict(motorl)
        assert len(motord) == len(motorl)
        return motord

    def motors_map(self, motors):
        pandas, = set(self.motors[m] for m in motors)
        return pandas

    def check(self, plan, *args, **kwargs):
        motors = motors_get(args[1:])[-1:]
        pandas = self.motors_map(motors)
        encoder_check(pandas[0], self.enc_tols, motors)
        vbas_check(self.vbas_ratios, args[1:], kwargs)

    def callback(self, plan, *args, **kwargs):
        return [HDF5Checker(self.h5_tols, args[0], args[-1]),
            self.U.mzcb, self.parent.progress]

class PmacPlanner(ChildPlanner):
    configs = BuboPlanner.configs

    def __init__(self, pandas, pmacs, *, drift,
        divs = {}, enc_tols = {}, configs = {}):
        super().__init__()
        self.drift, self.divs = drift, divs
        self.enc_tols, self._configs = enc_tols, configs
        self.motors = self.motors_prep(pandas, pmacs)
        for k, f in [
            ("fpmac_archim", fpmac_archim), ("fpmac_grid", fpmac_grid),
            ("fpmac_array", fpmac_array), ("fpmac_list", fpmac_list),
            ("fpmac_sarchim", fpmac_sarchim), ("fpmac_sgrid", fpmac_sgrid),
        ]:
            self.plans[k] = self.plan_wrap(k, f)

    def plan_wrap(self, k, f):
        return lambda *args, **kwargs: f(
            *(self.motors_map(self.motors_get(k, *args, **kwargs)) + args),
            div = [div_get(self.divs, args[0]), self.drift],
            configs = self.configs(k, *args, **kwargs), **kwargs
        )

    def fly_params(self, plan, *args, **kwargs):
        if plan not in ["fpmac_archim", "fpmac_grid"]:
            return kwargs["period"][1], sum(kwargs["period"])
        duty = auto_atom(kwargs.get("atom"), kwargs.get("duty"))[1]
        period = auto_velo(
            list(args[1 : 3]),
            args[4] if plan == "fpmac_archim" else
                abs(args[7] - args[6]) / (args[8] - 1),
            duty, *[kwargs.get(k) for k in
                ["period", "atime", "velocity"]]
        )[0]
        return duty * period, period

    def motors_prep(self, pandas, pmacs):
        motorl = [(m, tuple(ps)) for ps in pandas for m in ps[0].motors], \
            [(m, p) for p in pmacs for m in p.motors]
        motord = dict(motorl[0]), dict(motorl[1])
        assert len(motord[0]) == len(motorl[0]) and \
            len(motord[1]) == len(motorl[1])
        return {m: (motord[0][m], motord[1][m])
            for m in set(motord[0]) & set(motord[1])}

    def motors_map(self, motors):
        (pandas, pmac), = set(self.motors[m] for m in motors)
        return pandas, pmac

    def motors_get(self, plan, *args, **kwargs):
        if plan in ["fpmac_archim", "fpmac_grid",
            "fpmac_sarchim", "fpmac_sgrid"]:
            return list(args[1 : 3])
        elif plan in ["fpmac_array"]:
            return list(args[1])
        elif plan in ["fpmac_list"]:
            return [arg[0] for arg in args[1:]]
        return []

    def check(self, plan, *args, **kwargs):
        motors = self.motors_get(plan, *args, **kwargs)
        pandas, pmac = self.motors_map(motors)
        encoder_check(pandas[0], self.enc_tols, motors)

    def callback(self, plan, *args, **kwargs):
        return [self.U.mzcb, self.parent.progress]


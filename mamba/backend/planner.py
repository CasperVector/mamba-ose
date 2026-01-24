import os
from bluesky import plans
from bluesky.callbacks.core import CallbackBase
from butils.data import ImageFiller, my_broker
from butils.fly import auto_velo, fly_grid, fly_dgrid, sfly_grid
from butils.plans import motors_get, plan_fmt
from butils.traj import fpmac_archim, fpmac_grid, \
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

    def run(self, plan, *args, **kwargs):
        self.check(plan, *args, **kwargs)
        cb = self.callback(plan, *args, **kwargs)
        md = self.md_gen(plan, *args,
            md = kwargs.pop("md", None) or {}, **kwargs)
        return self.U.RE(self.plans[plan](*args, **kwargs, md = {
            "plan_cmd": plan_fmt(("P." + plan, args, kwargs))
        }), cb, md = md)

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
        if self.idx[0] % 2:
            return
        cur = self.idx[0] // 2 * self.num + self.idx[1]
        for det in self.dets:
            tol = self.tols.get(det)
            if tol is None:
                continue
            sig = det.hdf1.array_counter
            cnt = sig.get()
            if not (cur - tol <= cnt <= cur):
                raise RuntimeError(("Unexpected value of %s:" +
                    " %d, should be %d") % (sig.vname(), cnt, cur))

class BuboPlanner(ChildPlanner):
    def __init__(self, bubo, *, divs = {}, h5_tols = {}, configs = {}):
        super().__init__()
        self.bubo, self.divs = bubo, divs
        self.h5_tols, self._configs = h5_tols, configs
        self.plans["sfly_grid"] = lambda dets, *args, **kwargs: sfly_grid(
            self.bubo, dets, *args, div = div_get(self.divs, dets),
            configs = self.configs("sfly_grid", dets, *args, **kwargs), **kwargs
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
        self.pandas, self.divs = pandas, divs
        self.enc_tols, self._configs = enc_tols, configs
        self.h5_tols, self.vbas_ratios = h5_tols, vbas_ratios
        for k, f in [("fly_grid", fly_grid), ("fly_dgrid", fly_dgrid)]:
            self.plans[k] = (lambda k, f: lambda dets, *args, **kwargs: f(
                self.pandas, dets, *args, div = div_get(self.divs, dets),
                configs = self.configs(k, dets, *args, **kwargs), **kwargs
            ))(k, f)

    def check(self, plan, *args, **kwargs):
        encoder_check(self.pandas[0], self.enc_tols, motors_get(args[1:]))
        vbas_check(self.vbas_ratios, args[1:], kwargs)

    def callback(self, plan, *args, **kwargs):
        return [HDF5Checker(self.h5_tols, args[0], args[-1]),
            self.U.mzcb, self.parent.progress]

class PmacPlanner(ChildPlanner):
    configs = BuboPlanner.configs

    def __init__(self, pandas, pmac, *, drift,
        divs = {}, enc_tols = {}, configs = {}):
        super().__init__()
        self.pandas, self.pmac, self.divs = pandas, pmac, divs
        self.drift, self.enc_tols, self._configs = drift, enc_tols, configs
        for k, f in [
            ("fpmac_archim", fpmac_archim), ("fpmac_grid", fpmac_grid),
            ("fpmac_array", fpmac_array), ("fpmac_list", fpmac_list),
            ("fpmac_sarchim", fpmac_sarchim), ("fpmac_sgrid", fpmac_sgrid),
        ]:
            self.plans[k] = (lambda k, f: lambda dets, *args, **kwargs: f(
                self.pandas, self.pmac, dets, *args,
                div = [div_get(self.divs, dets), self.drift],
                configs = self.configs(k, dets, *args, **kwargs), **kwargs
            ))(k, f)

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
        encoder_check(self.pandas[0], self.enc_tols,
            self.motors_get(plan, *args, **kwargs))

    def callback(self, plan, *args, **kwargs):
        return [self.U.mzcb, self.parent.progress]


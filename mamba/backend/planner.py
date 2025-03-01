import os
from epics import caget
from bluesky import plans
from bluesky.callbacks.core import CallbackBase
from butils.data import ImageFiller, my_broker
from butils.fly import fly_dsimple, \
    fly_pcomp, fly_simple, sfly_simple, velo_simple
from butils.plans import motors_get, plan_fmt
from .progress import ProgressReporter, progressBars

class BasePlanner(object):
    plans, U = [], None

    def __init__(self):
        self.plans = {k: getattr(plans, k) for k in self.plans}

    def check(self, plan, *args, **kwargs):
        pass

    def callback(self, plan, *args, **kwargs):
        return [self.U.mzcb]

    def run(self, plan, *args, **kwargs):
        self.check(plan, *args, **kwargs)
        cb = self.callback(plan, *args, **kwargs)
        md = kwargs.pop("md", None) or {}
        return self.U.RE(self.plans[plan](*args, **kwargs, md = {
            "plan_cmd": plan_fmt(("P." + plan, args, kwargs))
        }), cb, md = md)

class ChildPlanner(BasePlanner):
    parent = None

class ParentPlanner(BasePlanner):
    def __init__(self, U):
        super().__init__()
        self.U, self.origins = U, [self]

    def extend(self, child):
        self.origins.append(child)
        child.U, child.parent = self.U, self

    def make_plans(self):
        ret = type("MambaPlans", (object,), {})()
        for obj in self.origins:
            for plan in obj.plans:
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

    def run(self, plan, *args, **kwargs):
        self.check(plan, *args, **kwargs)
        cb = self.callback(plan, *args, **kwargs)
        md = self.md_gen(plan, *args,
            md = kwargs.pop("md", None) or {}, **kwargs)
        return self.U.RE(self.plans[plan](*args, **kwargs, md = {
            "plan_cmd": plan_fmt(("P." + plan, args, kwargs))
        }), cb, md = md)

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

def div_get(divs, dets, num):
    div = 0
    for det in dets:
        if det in divs:
            div = max(div, divs[det])
    assert div >= num or not div
    return div // num

def encoder_check(panda, tols, motors):
    for motor in motors:
        inp, tol = panda.motors.get(motor), tols.get(motor)
        if inp is None or tol is None:
            continue
        delta = inp.calibrate(False)
        print("%s.motor_rmp - %s.value = %d" %
            (motor.vname(), inp.vname(), delta))
        if abs(delta) > tol:
            raise RuntimeError(("abs(%d) > %d; execute `%s.calibrate()'" +
                " and inform beamline operator") % (delta, tol, inp.vname()))

def vbas_check(ratios, args, kwargs):
    motor, lo, hi, num = args[-4:]
    ratio = ratios.get(motor)
    if ratio is None:
        return
    velocity = velo_simple(motor, lo, hi, num, kwargs["duty"],
        *(kwargs.get(k) for k in ["period", "velocity", "pad"]))[1]
    if velocity < ratio * caget(motor.prefix + ".VBAS"):
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
    def __init__(self, bubo, *, divs = {}, h5_tols = {}):
        super().__init__()
        self.h5_tols = h5_tols
        self.plans["sfly_grid"] = lambda dets, *args, **kwargs: sfly_simple\
            (bubo, dets, *args, div = div_get(divs, dets, args[-1]), **kwargs)

    def callback(self, plan, *args, **kwargs):
        return [HDF5Checker(self.h5_tols, args[0], args[-1]),
            self.U.mzcb, self.parent.progress]

class PandaPlanner(ChildPlanner):
    def __init__(self, panda, adp, *, divs = {}, h5_tols = {},
        enc_tols = {}, vbas_ratios = {}, configs = {}):
        super().__init__()
        self.panda, self.h5_tols, self.enc_tols, self.vbas_ratios = \
            panda, h5_tols, enc_tols, vbas_ratios
        for k, f in [("fly_grid", fly_simple),
            ("fly_dgrid", fly_dsimple), ("fly_pgrid", fly_pcomp)]:
            self.plans[k] = (lambda f: lambda dets, *args, **kwargs: f(
                panda, adp, dets, *args, configs = configs,
                div = div_get(divs, dets, args[-1]), **kwargs
            ))(f)

    def check(self, plan, *args, **kwargs):
        encoder_check(self.panda, self.enc_tols, motors_get(args[1:]))
        vbas_check(self.vbas_ratios, args[1:], kwargs)

    def callback(self, plan, *args, **kwargs):
        return [HDF5Checker(self.h5_tols, args[0], args[-1]),
            self.U.mzcb, self.parent.progress]


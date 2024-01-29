import os
from epics import caget
from bluesky.callbacks.core import CallbackBase
from mamba.backend.planner import MambaPlanner, ChildPlanner
from .data import ImageFiller, my_broker
from .fly import fly_simple, motors_get, sfly_simple, velo_simple

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
        self.idx = 0

    def event(self, doc):
        self.idx += 1
        if self.idx % 2:
            return
        cur = self.idx // 2 * self.num
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
        self.plans["fly_grid"] = lambda dets, *args, **kwargs: \
            fly_simple(panda, adp, dets, *args, div =
                div_get(divs, dets, args[-1]), configs = configs, **kwargs)

    def check(self, plan, *args, **kwargs):
        encoder_check(self.panda, self.enc_tols, motors_get(args[1:]))
        vbas_check(self.vbas_ratios, args[1:], kwargs)

    def callback(self, plan, *args, **kwargs):
        return [HDF5Checker(self.h5_tols, args[0], args[-1]),
            self.U.mzcb, self.parent.progress]


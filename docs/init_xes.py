import numpy
from bluesky import RunEngine
from ophyd import Component, Device
from ophyd.signal import AttributeSignal
from ophyd.sim import SynSignal
from butils.common import AttrDict
from butils.ophyd import CptLoad, EMotorLoad, MyEpicsMotor
from butils.sim import SimMotorImage
from mamba.attitude.common import img_polar
from mamba.attitude.xes_backend import sextend_xes
from mamba.backend.addon_core import sextend_core
from mamba.backend.mzserver import server_build

def my_gauss(x):
    return numpy.power(2, -4 * x ** 2)

class SimCam(Device):
    atime_ratio = 1e3
    temperature_actual = Component(SynSignal, func = lambda: -25.0)
    acquire_time = Component(AttributeSignal,
        attr = "_acquire_time", kind = "config")
    @property
    def _acquire_time(self):
        return round(self.parent.image.exposure_time * self.atime_ratio)
    @_acquire_time.setter
    def _acquire_time(self, x):
        self.parent.image.exposure_time = x / self.atime_ratio

class MySimImage(SimMotorImage):
    dim, gauss, lam = (2048, 2048), (400, 25), (1400, 0.66)
    origin, pos0, shift, fade = None, None, 10, (numpy.pi / 3, 1.0, 1.0)
    cam = Component(SimCam, "")
    def bind(self, motors):
        self.motors = motors
    def func(self):
        z = [self.motors[0].position - self.pos0[0],
            self.motors[1].position - self.pos0[1]]
        origin = self.origin + (self.shift, -self.shift) * numpy.array(z)
        rads, thetas = img_polar(self.dim[::-1], origin)
        z = z[0] + z[1] * 1j
        rad, theta = numpy.abs(z), numpy.angle(z) - numpy.pi
        ret = (thetas - theta) % (2 * numpy.pi) - numpy.pi
        ret = 1 - (self.fade[2] * rad) * my_gauss\
            (ret / (self.fade[0] * (1 + self.fade[1] * rad)))
        ret[ret < 0.0] = 0.0
        ret *= my_gauss((rads - self.gauss[0]) / self.gauss[1])
        ret = self.lam[1] + (1 - self.lam[1]) * ret
        return numpy.random.poisson(self.lam[0] * ret).astype("uint16")

def make_devs():
    C = AttrDict(l = CptLoad, m = EMotorLoad)
    M = AttrDict((k, C.m(MyEpicsMotor, "IOC:" + k)) for k in ["m1", "m2"])
    D = AttrDict(ad = C.l(MySimImage))
    return C, M, D

def proc_load(globals, added, removed):
    M, D, U = globals["M"], globals["D"], globals["U"]
    D.ad.origin = tuple((1024, 1024) + 100 * numpy.random.normal(size = (2,)))
    D.ad.pos0 = tuple(0.75 * numpy.random.normal(size = (2,)))
    U.atti_xes.origin_tol, U.atti_xes.xatol = 0.01, 0.01
    if "m1" in M and "m2" in M:
        D.ad.bind([M.m1, M.m2])
        D.ad.trigger().wait()
        U.atti_xes.bind(D.ad, [M.m1, M.m2])
    return []

def init(globals, config):
    print("Beamline init script loading...")
    globals["C"], globals["M"], globals["D"] = make_devs()
    globals["RE"] = RunEngine({})
    globals["U"] = U = server_build(globals, config)
    sextend_core(U, globals, config)
    sextend_xes(U)
    U.proc_load = lambda *args: proc_load(globals, *args)
    print("Failed devices:", U.proc_load(*U.loader.auto_load()))
    U.mzs.start()
    print("Beamline init script loaded.")


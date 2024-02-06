# Usage: python3 -m mamba.backend.zspawn 5678 \
#            ipython3 -i docs/example_init.py docs/example_config.yaml

print("Example beamline init script loading...")

import numpy
import time
from bluesky import RunEngine
from butils.common import AttrDict
from butils.ophyd import MyEpicsMotor
from butils.sim import SimMotorImage
from ophyd import Component, Device
from ophyd.signal import AttributeSignal
from ophyd.sim import SynSignal
from mamba.attitude.common import img_polar
from mamba.backend.mzserver import config_read, server_start

def my_gauss(x):
    return numpy.power(2, -4 * x ** 2)

class MyCam(Device):
    temperature_actual = Component(SynSignal, func = lambda: -25.0)
    acquire_time = Component(AttributeSignal,
        attr = "_acquire_time", kind = "config")
    @property
    def _acquire_time(self):
        return round(1e3 * self.parent.image.exposure_time)
    @_acquire_time.setter
    def _acquire_time(self, x):
        self.parent.image.exposure_time = 1e-3 * x

class MySimImage(SimMotorImage):
    dim, gauss, lam = (2048, 2048), (400, 25), (1400, 0.66)
    origin, pos0, shift, fade = None, None, 10, (numpy.pi / 3, 1.0, 1.0)
    cam = Component(MyCam, "")
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

M = AttrDict((k, MyEpicsMotor("IOC:" + k, name = "M." + k))
    for k in ["m1", "m2"])
D = AttrDict(ad = MySimImage(name = "D.ad"))
time.sleep(1.0)
D.ad.origin = tuple((1024, 1024) + 100 * numpy.random.normal(size = (2,)))
D.ad.pos0 = tuple(0.75 * numpy.random.normal(size = (2,)))
D.ad.bind([M.m1, M.m2])
D.ad.trigger().wait()

RE = RunEngine({})
U = server_start(globals(), config_read())
U.atti_xes.configure(D.ad, [M.m1, M.m2])
U.atti_xes.origin_tol = 0.01; U.atti_xes.xatol = 0.01

print("Beamline init script loaded.")


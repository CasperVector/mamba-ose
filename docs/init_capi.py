# Usage: python3 -m mamba.backend.zspawn 5678 \
#            ipython3 -i docs/example_init.py docs/example_config.yaml

print("Example beamline init script loading...")

import numpy
import time
from bluesky import RunEngine
from butils.common import AttrDict
from butils.ophyd import MyEpicsMotor
from butils.sim import SimMotorImage
from mamba.backend.mzserver import config_read, server_start

def rosenbrock(x):
    return (100.0 * (x[1:] - x[:-1] ** 2.0) ** 2.0 + (1 - x[:-1]) ** 2.0).sum(0)
def test_obj(x):
    return rosenbrock(x[:2]) + x[2] ** 2 + \
        numpy.random.normal(scale = 1e-2, size = x.shape[1:])
class MySimImage(SimMotorImage):
    def bind(self, motors):
        self.motors = motors
        return self.mbind(motors)
    def func(self):
        return test_obj(numpy.array([m.position for m in self.motors]))

M = AttrDict([
    (k, MyEpicsMotor("IOC:" + k, name = "M." + k))
    for k in ["m1", "m2", "m3"]
])
D = AttrDict([
    ("rosen", MySimImage(name = "D.rosen")),
])
time.sleep(1.0)
D.rosen.bind([M.m1, M.m2, M.m3])

RE = RunEngine({})
U = server_start(globals(), config_read())
U.atti_capi.configure(list(D.values()), list(M.values()))

print("Beamline init script loaded.")


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
from mamba.backend.planner import MambaPlanner
from lib_capi import CapiPlanner

def rosenbrock(x):
    return (100.0 * (x[1:] - x[:-1] ** 2.0) ** 2.0 + (1 - x[:-1]) ** 2.0).sum(0)
def test_obj1(x):
    return rosenbrock(x[:2]) + x[2] ** 2 + \
        numpy.random.normal(scale = 1e-2, size = x.shape[1:])
def test_obj2(x):
    return rosenbrock(x) + \
        numpy.random.normal(scale = 1e-2, size = x.shape[1:])
class MySimImage(SimMotorImage):
    def bind(self, obj, motors):
        self.obj, self.motors = obj, motors
        return self.mbind(motors)
    def func(self):
        return self.obj(numpy.array([m.position for m in self.motors]))

M = AttrDict([
    (k, MyEpicsMotor("IOC:" + k, name = "M." + k))
    for k in ["m1", "m2", "m3", "m4"]
])
D = AttrDict([
    ("rosen1", MySimImage(name = "D.rosen1")),
    ("rosen2", MySimImage(name = "D.rosen2")),
])
time.sleep(1.0)
D.rosen1.bind(test_obj1, [M.m1, M.m2, M.m3])
D.rosen2.bind(test_obj2, [M.m1, M.m2, M.m4])

RE = RunEngine({})
U = server_start(globals(), config_read())
U.atti_capi.configure(list(D.values()), list(M.values()))
U.planner = MambaPlanner(U)
U.planner.extend(CapiPlanner(U.atti_capi, M.values()))
P = U.planner.make_plans()

print("Beamline init script loaded.")


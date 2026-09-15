import numpy
from bluesky import RunEngine
from butils.common import AttrDict
from butils.ophyd import CptLoad, EMotorLoad, MyEpicsMotor
from butils.sim import SimMotorImage
from mamba.backend.addon_core import sextend_core
from mamba.backend.mzserver import server_build
from mamba.backend.planner import MambaPlanner
from mamba_site.lib_capi import CapiPlanner, sextend_capi

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

def make_devs():
    C = AttrDict(l = CptLoad, m = EMotorLoad)
    M = AttrDict([
        (k, C.m(MyEpicsMotor, "IOC:" + k))
        for k in ["m1", "m2", "m3", "m4"]
    ])
    D = AttrDict(
        rosen1 = C.l(MySimImage),
        rosen2 = C.l(MySimImage)
    )
    return C, M, D

def proc_load(globals, added, removed):
    M, D, U = globals["M"], globals["D"], globals["U"]
    if all(k in M for k in ["m1", "m2", "m3", "m4"]):
        D.rosen1.bind(test_obj1, [M.m1, M.m2, M.m3])
        D.rosen2.bind(test_obj2, [M.m1, M.m2, M.m4])
        D.rosen1.trigger().wait()
        D.rosen2.trigger().wait()
    U.atti_capi.bind(list(D.values()), list(M.values()))
    U.planner = MambaPlanner(U)
    U.planner.extend(CapiPlanner(U.atti_capi, M.values()))
    globals["P"] = U.planner.make_plans()
    return []

def init(globals, config):
    print("Beamline init script loading...")
    globals["C"], globals["M"], globals["D"] = make_devs()
    globals["RE"] = RunEngine({})
    globals["U"] = U = server_build(globals, config)
    sextend_core(U, globals, config)
    sextend_capi(U)
    U.proc_load = lambda *args: proc_load(globals, *args)
    print("Failed devices:", U.proc_load(*U.loader.auto_load()))
    U.mzs.start()
    print("Beamline init script loaded.")


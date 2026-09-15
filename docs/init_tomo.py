import numpy
from scipy.spatial import transform
from bluesky import RunEngine
from ophyd.sim import SynAxis
from butils.common import AttrDict
from butils.ophyd import CptLoad
from butils.sim import SimMotorImage
from mamba.attitude.common import img_polar
from mamba.backend.addon_core import sextend_core
from mamba.backend.mzserver import server_build
from mamba_site.lib_tomo import MyMambaPlanner, sextend_tomo

my_gauss = lambda x: numpy.power(2, -4 * x ** 2)
class MySimImage(SimMotorImage):
    dim, lam = (1536, 2048), (200, 0.1)
    pin, pos0 = (250, 1000, 8), None
    def bind(self, motors):
        self.motors = motors
    def func(self):
        euler = [m.position - p for m, p in zip(self.motors, self.pos0)]
        rot = transform.Rotation.from_euler("XZY", euler, degrees = True)
        v = rot.as_matrix() @ [0, self.pin[1], self.pin[0]]
        xy = self.dim[0] / 2 + v[0], self.dim[1] / 2 + self.pin[1] - v[1]
        ret = my_gauss(img_polar(self.dim[1::-1], xy)[0] / self.pin[2])
        return numpy.random.poisson(self.lam[0] * ret + self.lam[1])

def make_devs():
    C = AttrDict(l = CptLoad)
    M = AttrDict((k, C.l(SynAxis, labels = {"motors"}))
        for k in ["pitch", "roll", "yaw"])
    D = AttrDict(ad = C.l(MySimImage))
    return C, M, D

def proc_load(globals, added, removed):
    M, D, U = globals["M"], globals["D"], globals["U"]
    D.ad.pos0 = numpy.random.uniform(-5.0, 5.0, (3,))
    D.ad.bind([M.pitch, M.roll, M.yaw])
    D.ad.trigger().wait()
    U.planner = MyMambaPlanner(U)
    globals["P"] = P = U.planner.make_plans()
    U.atti_tomo.bind([D.ad], [M.pitch, M.roll], [M.yaw], P)
    return []

def init(globals, config):
    print("Beamline init script loading...")
    globals["C"], globals["M"], globals["D"] = make_devs()
    globals["RE"] = RunEngine({})
    globals["U"] = U = server_build(globals, config)
    sextend_core(U, globals, config)
    sextend_tomo(U)
    U.proc_load = lambda *args: proc_load(globals, *args)
    print("Failed devices:", U.proc_load(*U.loader.auto_load()))
    U.mzs.start()
    print("Beamline init script loaded.")


# Usage: python3 -m mamba.backend.zspawn 5678 \
#            ipython3 -i docs/example_init.py docs/example_config.yaml

print("Example beamline init script loading...")

import numpy
from scipy.spatial import transform
from bluesky import RunEngine
from butils.common import AttrDict
from butils.sim import SimMotorImage
from ophyd.sim import SynAxis
from mamba.attitude.common import img_polar
from mamba.backend.mzserver import config_read, server_start
from lib_tomo import MyMambaPlanner

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

M = AttrDict((k, SynAxis(name = "M." + k, labels = {"motors"}))
    for k in ["pitch", "roll", "yaw"])
D = AttrDict(ad = MySimImage(name = "D.ad"))
D.ad.pos0 = numpy.random.uniform(-5.0, 5.0, (3,))
D.ad.bind([M.pitch, M.roll, M.yaw])
D.ad.trigger().wait()

RE = RunEngine({})
U = server_start(globals(), config_read())
U.planner = MyMambaPlanner(U)
P = U.planner.make_plans()
U.atti_tomo.configure([D.ad], [M.pitch, M.roll], [M.yaw], P)

print("Beamline init script loaded.")


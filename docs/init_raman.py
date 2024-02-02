# Usage: python3 -m mamba.backend.zspawn 5678 \
#            ipython3 -i docs/example_init.py docs/example_config.yaml

print("Example beamline init script loading...")

import numpy
import time
from bluesky import RunEngine
from butils.common import AttrDict
from butils.ophyd import MyEpicsMotor, QueueMotor
from butils.sim import SimMotorImage
from mamba.attitude.common import img_polar
from mamba.backend.mzserver import config_read, server_start

nmod = 1
my_gauss = lambda x: numpy.power(2, -4 * x ** 2)
class MySimImage(SimMotorImage):
    dim, gauss, lam = (280, 240, 6), (4, 12, 20), (200, 0.1)
    origins = motors = None
    def bind(self, motors, origins):
        self.motors, self.origins = motors, origins
        return self.mbind(motors)
    def func(self):
        ret = numpy.zeros(self.dim[1::-1], dtype = "float64")
        ratio = min(self.dim[:2]) / self.dim[2]
        for i, (x, y, mu) in enumerate(self.origins):
            origin = x + ratio * self.motors[3 * i + 1].position, \
                y + ratio * self.motors[3 * i + 2].position
            fwhm = self.gauss[0] + self.gauss[1] * (1 - my_gauss\
                ((self.motors[3 * i].position - mu) / self.gauss[2]))
            ret += (self.gauss[0] / fwhm) ** 1.75 * \
                my_gauss(img_polar(self.dim[1::-1], origin)[0] / fwhm)
        return numpy.random.poisson(self.lam[0] * ret + self.lam[1])

M = AttrDict()
M.update([
    (name, MyEpicsMotor("IOC:" + name, name = "M." + name))
    for name in ["m%d" % (i + 1) for i in range(5 + 2)]
])
M.update([
    (name, QueueMotor("B5:%s:" % name, name = "M." + name)) for name in
    ["mhaydon%d%d_sub%d" % (i, j, k) for i in range(nmod)
        for j in range(5) for k in range(3)] +
    ["mopto%d%d_sub%d" % (i, j, k) for i in range(nmod)
        for j in range(2) for k in range(15)]
])
D = AttrDict(ad = MySimImage(name = "D.ad"))
D.ad.monitor_period.set(0.2)
time.sleep(1.0)

RE = RunEngine({})
U = server_start(globals(), config_read())
U.monitor_periods["monitor/position"] = 0.2
[d.monitor(U.lnotify) for d in list(M.values()) + [D.ad]]
[M[m].configure({"velocity": 8.0,
    "low_limit_travel": -10000.0, "high_limit_travel": 10000.0,
}) for m in M if "_sub" not in m]
origins = [6 * i - 42 for i in range(15)], \
    [(56 * (i // 3) + 28, 80 * (i % 3) + 40) for i in range(15)]
numpy.random.shuffle(origins[0]); numpy.random.shuffle(origins[1])
mm = sum([[
    M["mhaydon%d%d_sub%d" % (i, j // 3, j % 3)],
    M["mopto%d0_sub%d" % (i, j)], M["mopto%d1_sub%d" % (i, j)],
] for i in range(nmod) for j in range(15)], [])
D.ad.bind(mm, [(x, y, mu) for mu, (x, y) in zip(origins[0], origins[1])])
U.atti_raman.configure(D.ad, mm,
    [(-50, 50), (-4.5, 4.5), (-4.5, 4.5)] * (nmod * 15))

del nmod, origins, mm
print("Beamline init script loaded.")


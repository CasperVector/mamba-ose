# Use with the files docs/raman_*

import numpy
from bluesky import RunEngine
from butils.common import AttrDict, fill_elems
from butils.ophyd import CptLoad, EMotorLoad, \
    QMotorLoad, MyEpicsMotor, QueueMotor
from butils.sim import SimMotorImage
from mamba.attitude.common import img_polar
from mamba.attitude.raman_backend import sextend_raman
from mamba.backend.addon_core import sextend_core
from mamba.backend.mzserver import server_build

BASES, MODS = ["vb", "vu", "vd", "hb", "hl", "hr"], [0]
QMOTORS = [(BASES[i], "abcde"[j // 3], j % 3 + 1)
    for i in MODS for j in range(15)]
QMOTORS = [s % k for k in QMOTORS for s in
    ["%s_%s%d_foc", "%s_%s%d_th", "%s_%s%d_chi"]]
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

def make_devs():
    C = AttrDict(l = CptLoad, m = EMotorLoad, q = QMotorLoad)
    M = AttrDict([(k, C.m(MyEpicsMotor, "IOC:" + k)) for k in
        ["m%d" % (i + 1) for i in range(len(MODS) * 7)]])
    M.update([(name, C.q(QueueMotor, "B5:%s:" % name)) for name in QMOTORS])
    D = AttrDict(ad = C.l(MySimImage))
    return C, M, D

def proc_load(globals, added, removed):
    M, D, U = globals["M"], globals["D"], globals["U"]
    U.monitor_periods["monitor/position"] = 0.2
    [M[k].configure({"velocity": 8.0,
        "low_limit_travel": -10000.0, "high_limit_travel": 10000.0,
    }) for k in M if k.startswith("m")]
    D.ad.configure({"monitor_period": 0.2})
    mm = fill_elems(M, QMOTORS)
    [o.monitor(U.lnotify) for o in mm + [D.ad]]
    if all(k in M for k in QMOTORS):
        origins = [6 * i - 42 for i in range(15)], \
            [(56 * (i // 3) + 28, 80 * (i % 3) + 40) for i in range(15)]
        numpy.random.shuffle(origins[0]); numpy.random.shuffle(origins[1])
        D.ad.bind(mm, [(x, y, mu) for mu, (x, y) in
            zip(origins[0], origins[1])])
        D.ad.trigger().wait()
        U.atti_raman.bind(D.ad, mm,
            [(-50, 50), (-4.5, 4.5), (-4.5, 4.5)] * (len(MODS) * 15))
    return []

def init(globals, config):
    print("Beamline init script loading...")
    globals["C"], globals["M"], globals["D"] = make_devs()
    globals["RE"] = RunEngine({})
    globals["U"] = U = server_build(globals, config)
    sextend_core(U, globals, config)
    sextend_raman(U)
    U.proc_load = lambda *args: proc_load(globals, *args)
    print("Failed devices:", U.proc_load(*U.loader.auto_load()))
    U.mzs.start()
    print("Beamline init script loaded.")


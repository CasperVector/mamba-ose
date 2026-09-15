import numpy
from bluesky import RunEngine
from ophyd.sim import SynAxis, SynGauss, DirectImage
from butils.common import AttrDict
from butils.ophyd import CptLoad
from mamba.backend.addon_core import sextend_core
from mamba.backend.mzserver import server_build
from mamba.backend.planner import MambaPlanner
from mamba.gengyd.auth_mdg import sextend_gydauthmdg

def make_devs():
    C = AttrDict(l = CptLoad)
    M = AttrDict(
        motor1 = C.l(SynAxis, labels = {"motors"}),
        motor2 = C.l(SynAxis, labels = {"motors"})
    )
    D = AttrDict(
        image = C.l(DirectImage, labels = {"detectors"},
            func = lambda: numpy.array(numpy.ones((10, 10))))
    )
    return C, M, D

def proc_load(globals, added, removed):
    M, D, U = globals["M"], globals["D"], globals["U"]
    if "det" in D:
        D.pop("det").destroy()
    if "motor" in M:
        D.det = SynGauss("D.det", M.motor1, "M_motor1",
            center = 0, Imax = 1, sigma = 1, labels = {"detectors"})
    U.planner = MambaPlanner(U)
    globals["P"] = U.planner.make_plans()
    return []

def init(globals, config):
    print("Beamline init script loading...")
    globals["C"], globals["M"], globals["D"] = make_devs()
    globals["RE"] = RunEngine({})
    globals["U"] = U = server_build(globals, config)
    sextend_core(U, globals, config)
    sextend_gydauthmdg(U, config)
    U.proc_load = lambda *args: proc_load(globals, *args)
    print("Failed devices:", U.proc_load(*U.loader.auto_load()))
    U.mzs.start()
    print("Beamline init script loaded.")


# Use with the files docs/hr_*

import os
from bluesky import RunEngine
from butils.ad import ADCore
from butils.common import AttrDict, fn_wait
from butils.ophyd import EpicsLoad, EMotorLoad, \
    ADetLoad, MyEpicsMotor, HREnergy, SimpleDet
from mamba.backend.addon_core import sextend_core
from mamba.backend.mzserver import server_build
from mamba.backend.planner import ImagePlanner
from mamba.gengyd.auth_mdg import sextend_gydauthmdg

def make_devs():
    C = AttrDict(e = EpicsLoad, m = EMotorLoad,
        ad = ADetLoad, en = EpicsLoad.new_suffix("ERdbkAO"))
    M = AttrDict(
        m1 = C.m(MyEpicsMotor, "IOC:m1"),
        m2 = C.m(MyEpicsMotor, "IOC:m2"),
        m3 = C.m(MyEpicsMotor, "IOC:m3"),
        ehr = C.en(HREnergy, "IOC:HR1_", settle_time = 0.25)
    )
    D = AttrDict(
        k648x = C.e(SimpleDet, "IOC:6485"),
        ad = C.ad(ADCore, "13SIM1:", hdf5_dir = os.getcwd() + "/big")
    )
    return C, M, D

def proc_load(globals, added, removed):
    M, D, U = globals["M"], globals["D"], globals["U"]
    if "ehr" in M and "m1" in M:
        M.ehr.resetter = M.m1
    ret = [d for d in D.values() if hasattr(d, "warmup")]
    ret = ret, fn_wait([d.warmup for d in ret])[1]
    ret = [d.vname() for d, s in zip(ret[0], ret[1]) if s]
    U.loader.unload(ret)
    U.planner = ImagePlanner(U)
    globals["P"] = U.planner.make_plans()
    return ret

def init(globals, config):
    print("Beamline init script loading...")
    #from concurrent import futures
    #from butils.common import threadpool_shutdown
    #futures.ThreadPoolExecutor.shutdown = threadpool_shutdown
    globals["C"], globals["M"], globals["D"] = make_devs()
    globals["RE"] = RunEngine({})
    globals["U"] = U = server_build(globals, config)
    sextend_core(U, globals, config)
    sextend_gydauthmdg(U, config)
    U.proc_load = lambda *args: proc_load(globals, *args)
    print("Failed devices:", U.proc_load(*U.loader.auto_load()))
    U.mzs.start()
    print("Beamline init script loaded.")


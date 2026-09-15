import os
from bluesky import RunEngine
from ophyd.device import STAGE_KEEP
from butils.ad import ADPandABlocks, ADXspress3
from butils.bubo import BuboDevice
from butils.common import AttrDict, fill_elems, fill_keys, fill_vals, fn_wait
from butils.fly import prep_dseq, seq_dwarmup
from butils.ophyd import CptLoad, EMotorLoad, \
    ADetLoad, PandaLoad, MyEpicsMotor
from butils.panda import PandaDevice
from mamba.backend.addon_core import sextend_core
from mamba.backend.mzserver import server_build
from mamba.backend.planner import ImagePlanner
from mamba_site.lib_fly import MyPandaPlanner, MyBuboPlanner

def make_devs():
    C = AttrDict(l = CptLoad, m = EMotorLoad, ad = ADetLoad, pl = PandaLoad)
    M = AttrDict(
        m1 = C.m(MyEpicsMotor, "kohzu:m1"),
        m2 = C.m(MyEpicsMotor, "kohzu:m2"),
        m3 = C.m(MyEpicsMotor, "kohzu:m3")
    )
    D = AttrDict(
        xsp3 = C.ad(ADXspress3, "13XSP3:", hdf5_dir = os.getcwd() + "/big"),
        adp = C.ad(ADPandABlocks, "PANDA1:", hdf5_dir = os.getcwd() + "/big"),
        panda = C.pl(PandaDevice, "192.168.1.11"),
        bubo = C.l(BuboDevice, write_dir = os.getcwd() + "/big")
    )
    return C, M, D

def proc_load(globals, added, removed):
    M, D, U = globals["M"], globals["D"], globals["U"]
    for m in M.values():
        m.stage_sigs.update({"velocity": STAGE_KEEP})
        m.velocity.set(4.0).wait()
    if "panda" in D:
        D.panda.ad = D.get("adp")
        D.panda.clear_muxes()
        D.panda.clear_capture()
        prep_dseq(D.panda, [("ttlout1.val", "b")],
            fill_vals(M, [("inenc1.val", "m1"), ("inenc2.val", "m2")]))
        D.panda.configure(seq_dwarmup(), action = True)
    ret = [d for d in D.values() if hasattr(d, "warmup")]
    ret = ret, fn_wait([d.warmup for d in ret])[1]
    ret = [d.vname() for d, s in zip(ret[0], ret[1]) if s]
    U.loader.unload(ret)
    if "panda" in D:
        D.panda.configure({"dseq.enable": 0, "pcap.enable": "ZERO"})
    U.planner = ImagePlanner(U)
    pandas = [(p,) for p in fill_elems(D, ["panda"])]
    pmotors = [m for ps in pandas for m in ps[0].motors]
    divs = dict(fill_keys(D, [("xsp3", 12216)]))
    h5_tols = {d: 0 for d in D.values() if hasattr(d, "config_fly")},
    U.planner.extend(MyPandaPlanner(
        pandas, divs = divs, h5_tols = h5_tols,
        enc_tols = {m: 0.025 for m in pmotors},
        vbas_ratios = {m: 2.0 for m in pmotors},
        configs = {d: d.config_fly() for d in fill_elems(D, ["xsp3"])}
    ))
    U.planner.extend(MyBuboPlanner(D.bubo, divs = divs, h5_tols = h5_tols))
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
    U.proc_load = lambda *args: proc_load(globals, *args)
    print("Failed devices:", U.proc_load(*U.loader.auto_load()))
    U.mzs.start()
    print("Beamline init script loaded.")


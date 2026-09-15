from bluesky import RunEngine
from ophyd.device import STAGE_KEEP
from butils.ad import QDPanda
from butils.common import AttrDict, fill_elems, fill_vals, fn_wait
from butils.fly import prep_dseq
from butils.ophyd import EpicsLoad, EMotorLoad, QDetLoad, PandaLoad
from butils.panda import PandaDevice
from butils.plans import ctrans_reg
from butils.traj import PmacMotor, PmacTraj
from mamba.backend.addon_core import sextend_core
from mamba.backend.mzserver import server_build
from mamba.backend.planner import MambaPlanner, PandaPlanner, PmacPlanner
from mamba_site.lib_ptycho import fparams_grid3, \
    fpmac_grid3, fpmac_sgrid3, make_step_plans, step_array

class MyMambaPlanner(MambaPlanner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plans.update(make_step_plans(step_array))

class MyPmacPlanner(PmacPlanner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for k, f in [("fpmac_grid3", fpmac_grid3),
            ("fpmac_sgrid3", fpmac_sgrid3)]:
            self.plans[k] = self.plan_wrap(k, f)

    def fly_params(self, plan, *args, **kwargs):
        if plan in ["fpmac_grid3"]:
            return fparams_grid3(*args, **kwargs)
        return super().fly_params(plan, *args, **kwargs)

    def motors_get(self, plan, *args, **kwargs):
        if plan in ["fpmac_grid3", "fpmac_sgrid3"]:
            return list(args[2 : 5])
        return super().motors_get(plan, *args, **kwargs)

def make_devs():
    C = AttrDict(m = EMotorLoad, qd = QDetLoad, pl = PandaLoad,
        pt = EpicsLoad.new_suffix("ProfileNumPoints"))
    M = AttrDict([
        ("brick1_" + s, C.m(PmacMotor, "BRICK1:%s" % s.upper()))
        for s in ["m2", "m3", "m4"]
    ] + [("brick1_pmac", C.pt(PmacTraj, "BRICK1:"))])
    D = AttrDict(
        qdp1 = C.qd(QDPanda, "panda1:"),
        qdp2 = C.qd(QDPanda, "panda2:"),
        panda1 = C.pl(PandaDevice, "10.5.131.15"),
        panda2 = C.pl(PandaDevice, "10.5.131.16")
    )
    return C, M, D

def proc_load(globals, added, removed):
    M, D, U = globals["M"], globals["D"], globals["U"]
    pmotors = fill_elems(M, ["brick1_" + m for m in ["m2", "m3", "m4"]])
    if "brick1_pmac" in M:
        M.brick1_pmac.motors = pmotors
    for m in pmotors:
        m.stage_sigs.update({"velocity": STAGE_KEEP})
        m.velocity.set(3.0).wait()
    if "panda1" in D:
        D.panda1.ad = D.get("qdp1")
        D.panda1.clear_muxes(); D.panda1.clear_capture()
        prep_dseq(D.panda1, [("ttlout1.val", "b")], fill_vals(M, [
            ("fmc_in.val1", "brick1_m2"),
            ("fmc_in.val2", "brick1_m3"),
            ("fmc_in.val3", "brick1_m4"),
        ]) + [
            ("inenc1.val", None), ("inenc2.val", None),
            ("inenc3.val", None), ("inenc4.val", None),
        ])
    if "panda2" in D:
        D.panda2.ad = D.get("qdp2")
        D.panda2.clear_muxes(); D.panda2.clear_capture()
        prep_dseq(D.panda2, [("ttlout1.val", "b")], [
            ("inenc1.val", None), ("inenc2.val", None),
            ("inenc3.val", None), ("inenc4.val", None),
        ])
        D.panda2.configure({"seq%s.bita" % c: "TTLIN1.VAL" for c in "12"})
    ret = [d for d in D.values() if hasattr(d, "warmup")]
    ret = ret, fn_wait([d.warmup for d in ret])[1]
    ret = [d.vname() for d, s in zip(ret[0], ret[1]) if s]
    U.loader.unload(ret)
    U.planner = MyMambaPlanner(U)
    pandas = [tuple(fill_elems(D, ks)) for ks in
        [("panda1", "panda2")] if ks[0] in D]
    pmacs = fill_elems(M, ["brick1_pmac"])
    enc_tols = {m: 0.5 for ps in pandas for m in ps[0].motors}
    U.planner.extend(PandaPlanner(pandas, enc_tols = enc_tols))
    U.planner.extend(MyPmacPlanner(
        pandas, pmacs, drift = 1e6, enc_tols = enc_tols))
    globals["P"] = U.planner.make_plans()
    return ret

def init(globals, config):
    print("Beamline init script loading...")
    #from concurrent import futures
    #from butils.common import threadpool_shutdown
    #futures.ThreadPoolExecutor.shutdown = threadpool_shutdown
    ctrans_reg()
    globals["C"], globals["M"], globals["D"] = make_devs()
    globals["RE"] = RunEngine({})
    globals["U"] = U = server_build(globals, config)
    sextend_core(U, globals, config)
    U.proc_load = lambda *args: proc_load(globals, *args)
    print("Failed devices:", U.proc_load(*U.loader.auto_load()))
    U.mzs.start()
    print("Beamline init script loaded.")


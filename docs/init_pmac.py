# Usage: python3 -m mamba.backend.zspawn 5678 \
#            ipython3 -i docs/example_init.py docs/example_config.yaml

print("Example beamline init script loading...")

from bluesky import RunEngine
from ophyd.device import STAGE_KEEP
from butils.ad import make_qzdetector
from butils.common import AttrDict
from butils.fly import prep_dseq
from butils.panda import PandaDevice
from butils.plans import ctrans_reg
from butils.traj import PmacMotor, PmacTraj
from mamba.backend.mzserver import config_read, server_start
from mamba.backend.planner import MambaPlanner, PandaPlanner, PmacPlanner

QZDetector2 = make_qzdetector("QZDetector", 2)
M = AttrDict([
    ("brick1_" + s, PmacMotor("BRICK1:%s" % s.upper(),
        name = "M.brick1_%s" % s)) for s in ["m2", "m3", "m4"]
] + [("brick1_pmac", PmacTraj("BRICK1:", name = "M.brick1_pmac"))])
M.brick1_pmac.motors = [M["brick1_" + s for s in ["m2", "m3", "m4"]]]
D = AttrDict(
    qdp1 = QZDetector2("panda1:", name = "D.qdp1"),
    qdp2 = QZDetector2("panda2:", name = "D.qdp2")
)
D.panda1 = PandaDevice("10.5.131.15", name = "D.panda1", ad = D.qdp1)
D.panda2 = PandaDevice("10.5.131.16", name = "D.panda2", ad = D.qdp2)

[M["brick1_" + m].stage_sigs.update\
    ({"velocity": STAGE_KEEP}) for m in ["m2", "m3", "m4"]]
[M["brick1_" + m].velocity.set(3.0).wait() for m in ["m2", "m3", "m4"]]
D.panda1.clear_muxes(); D.panda1.clear_capture()
prep_dseq(D.panda1, [("ttlout1.val", "b")], [
    ("fmc_in.val1", M.brick1_m2),
    ("fmc_in.val2", M.brick1_m3),
    ("fmc_in.val3", M.brick1_m4),
    ("inenc1.val", None), ("inenc2.val", None),
    ("inenc3.val", None), ("inenc4.val", None),
])
D.panda2.clear_muxes(); D.panda2.clear_capture()
prep_dseq(D.panda2, [("ttlout1.val", "b")], [
    ("inenc1.val", None), ("inenc2.val", None),
    ("inenc3.val", None), ("inenc4.val", None),
])
D.panda2.configure({"seq%s.bita" % c: "TTLIN1.VAL" for c in "12"})
D.qdp1.configure({"num_images": 0})
D.qdp2.configure({"num_images": 0})

ctrans_reg()
RE = RunEngine({})
U = server_start(globals(), config_read())
U.planner = MambaPlanner(U)
U.planner.extend(PandaPlanner([(D.panda1, D.panda2)],
    enc_tols = {m: 0.5 for m in D.panda1.motors}))
U.planner.extend(PmacPlanner([(D.panda1, D.panda2)], [M.brick1_pmac],
    drift = 1e6, enc_tols = {m: 0.5 for m in D.panda1.motors}))
P = U.planner.make_plans()

print("Beamline init script loaded.")


# Usage: python3 -m mamba.backend.zspawn 5678 \
#            ipython3 -i docs/example_init.py docs/example_config.yaml

print("Example beamline init script loading...")

import os
from bluesky import RunEngine
from ophyd.device import STAGE_KEEP
from butils.ad import BaseAreaDetector
from butils.bubo import BuboDevice
from butils.common import AttrDict, fn_wait
from butils.fly import prep_dseq, seq_dwarmup
from butils.ophyd import MyEpicsMotor
from butils.panda import PandaDevice
from mamba.backend.mzserver import config_read, server_start
from mamba.backend.planner import ImagePlanner
from lib_fly import MyPandaPlanner, MyBuboPlanner

M = AttrDict(
    m1 = MyEpicsMotor("kohzu:m1", name = "M.m1"),
    m2 = MyEpicsMotor("kohzu:m2", name = "M.m2"),
    m3 = MyEpicsMotor("kohzu:m3", name = "M.m3")
)
D = AttrDict(
    bubo = BuboDevice(name = "D.bubo"),
    panda = PandaDevice("192.168.1.11", name = "D.panda"),
    adp = BaseAreaDetector("PANDA1:", name = "D.adp"),
    xsp3 = BaseAreaDetector("13XSP3:", name = "D.xsp3")
)

[m.stage_sigs.update({"velocity": STAGE_KEEP}) for m in M.values()]
[m.velocity.set(4.0).wait() for m in M.values()]
D.panda.clear_muxes()
D.panda.clear_capture()
prep_dseq(D.panda, [("ttlout1.val", "a")],
    [("inenc1.val", M.m1), ("inenc2.val", M.m2)])
D.panda.configure(seq_dwarmup(), action = True)
D.bubo.write_dir = os.getcwd() + "/big"
D.adp.hdf1.write_path_template = os.getcwd() + "/big"
D.adp.cam.configure({"image_mode": 1, "num_images": 1})
D.xsp3.hdf1.write_path_template = os.getcwd() + "/big"
D.xsp3.stage_sigs.update\
    ({"cam.trigger_mode": STAGE_KEEP, "cam.num_images": STAGE_KEEP})
D.xsp3.cam.configure({"trigger_mode": 1, "num_images": 1, "acquire_time": 0.1})
assert fn_wait([D[det].warmup for det in ["adp", "xsp3"]])

D.panda.configure({"dseq.enable": 0, "pcap.enable": "ZERO"})
D.adp.cam.image_mode.set(2).wait()
RE = RunEngine({})
U = server_start(globals(), config_read())
U.planner = ImagePlanner(U)
U.planner.extend(MyPandaPlanner(
    D.panda, D.adp, divs = {D.xsp3: 12216}, h5_tols = {D.xsp3: 0},
    enc_tols = {m: 25 for m in M}, vbas_ratios = {m: 2.0 for m in M},
    configs = {D.xsp3: {"cam.trigger_mode": 3}}
))
U.planner.extend(MyBuboPlanner(D.bubo,
    divs = {D.xsp3: 12216}, h5_tols = {D.xsp3: 0}))
P = U.planner.make_plans()

print("Beamline init script loaded.")


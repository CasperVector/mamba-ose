# Usage: python3 -m mamba.backend.zspawn 5678 \
#            ipython3 -i docs/example_init.py docs/example_config.yaml
# (Use with the files docs/hr_*)

print("Example beamline init script loading...")

import os
from bluesky import RunEngine
from butils.ad import MyAreaDetector
from butils.common import AttrDict
from butils.ophyd import MyEpicsMotor, HREnergy, SimpleDet
from mamba.backend.mzserver import config_read, server_start
from mamba.backend.planner import ImagePlanner

M = AttrDict(
    m1 = MyEpicsMotor("IOC:m1", name = "M.m1"),
    m2 = MyEpicsMotor("IOC:m2", name = "M.m2"),
    m3 = MyEpicsMotor("IOC:m3", name = "M.m3")
)
M.ehr = HREnergy("IOC:HR1_", name = "M.ehr",
    settle_time = 0.25, resetter = M.m1)

D = AttrDict(
    k648x = SimpleDet("IOC:6485", name = "D.k648x"),
    ad = MyAreaDetector("13SIM1:", name = "D.ad")
)
D.ad.hdf1.write_path_template = os.getcwd() + "/big"
D.ad.cam.configure\
    ({"trigger_mode": 0, "image_mode": 1, "num_images": 1})
D.ad.warmup()

RE = RunEngine({})
U = server_start(globals(), config_read())
U.planner = ImagePlanner(U)
P = U.planner.make_plans()

print("Beamline init script loaded.")


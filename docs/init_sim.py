# Usage: python3 -m mamba.backend.zspawn 5678 \
#            ipython3 -i docs/example_init.py docs/example_config.yaml

print("Example beamline init script loading...")

import numpy
from bluesky import RunEngine
from ophyd.sim import SynAxis, SynGauss, DirectImage
from butils.common import AttrDict
from mamba.backend.mzserver import config_read, server_start
from mamba.backend.planner import MambaPlanner

M = AttrDict(
    motor1 = SynAxis(name = "M.motor1", labels = {"motors"}),
    motor2 = SynAxis(name = "M.motor2", labels = {"motors"})
)

D = AttrDict(
    det = SynGauss("D.det", M.motor1, "M_motor1",
        center = 0, Imax = 1, sigma = 1, labels = {"detectors"}),
    image = DirectImage(func = lambda: numpy.array(numpy.ones((10, 10))),
        name = "D.image", labels = {"detectors"})
)

RE = RunEngine({})
U = server_start(globals(), config_read())
U.planner = MambaPlanner(U)
P = U.planner.make_plans()

print("Beamline init script loaded.")


# Usage: python3 ./mamba_server/zspawn.py 5678 ipython3 \
#            --InteractiveShellApp.exec_files='["docs/example_init.py"]'

print("Example beamline init script loading...")

from bluesky import RunEngine
from ophyd.sim import SynAxis, SynGauss, DirectImage, np
from utils.general_utils import AttrDict
from mamba_server.mzserver import server_start

M = AttrDict(
    motor1 = SynAxis(name = "M.motor1", labels = {"motors"}),
    motor2 = SynAxis(name = "M.motor2", labels = {"motors"})
)

D = AttrDict(
    det = SynGauss("D.det", M.motor1, "M_motor1",
        center = 0, Imax = 1, sigma = 1, labels = {"detectors"}),
    image = DirectImage(func = lambda: np.array(np.ones((10, 10))),
        name = "D.image", labels = {"detectors"})
)

RE = RunEngine({})
mzs = server_start(M, D, RE)

print("Beamline init script loaded.")


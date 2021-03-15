# Usage: python3 ./mamba_server/zspawn.py 5678 ipython3 \
#            --InteractiveShellApp.exec_files='["docs/example_init.py"]'

print("Example beamline init script loading...")

from mamba_server.server_start import server_start
from bluesky import RunEngine
from ophyd.sim import motor1, motor2, det, direct_img

RE = RunEngine({})
motors, dets = server_start(RE,
    {"mSampleX": motor1, "mSampleZ": motor2},
    {"det": det, "direct_img": direct_img})

print("Beamline init script loaded.")


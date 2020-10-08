# Beamline devices initialization script.
# =========================================
# A dictionary __registered_devices should be defined in this file.
# It is of the type: Dict[DeviceType, Dict[str, Any]]
# The _Any_ here is actually the device object. It can be a ophyd object,
# or other objects providing similar interface as an ohpyd.

from typing import Dict, Any

from . import DeviceType
import ophyd
from ophyd import EpicsMotor
from .device.eiger_ophyd import EigerOphyd, Eiger
import logging
import os

__registered_devices: Dict[DeviceType, Dict[str, Any]]

# motor_init_list = [
#     ('slitsH', 'BL3W1:stage_slits:motorH', 'motorH'),
#     ('slitsV', 'BL3W1:stage_slits:motorV', 'motorV'),
#     ('sampleX', 'BL3W1:stage_sample:motorX', 'motorX'),
#     ('sampleZ', 'BL3W1:stage_sample:motorZ', 'motorZ'),
#     ('sampleRoll', 'BL3W1:stage_sample:motorRoll', 'motorRoll'),
#     ('samplePitch', 'BL3W1:stage_sample:motorPitch', 'motorPitch'),
#     ('detX', 'BL3W1:stage_detector:motorX', 'motorX'),
#     ('detY', 'BL3W1:stage_detector:motorY', 'motorY'),
#     ('detZ', 'BL3W1:stage_detector:motorZ', 'motorZ'),
#     ('sampleR', 'BL3W1:sample:rotation', 'rotation'),
#     ('sample0', 'BL3W1:sample:sample0', 'sample0'),
#     ('sample90', 'BL3W1:sample:sample90', 'sample90'),
# ]
#
# motors = {}
#
# for m in motor_init_list:
#     try:
#         motors[m[0]] = EpicsMotor(m[1], name=m[2])
#         motors[m[0]].read()
#     except (ophyd.signal.ConnectionTimeoutError,
#             ophyd.utils.errors.DisconnectedError):
#         del motors[m[0]]
#         print(f"Unable to load motor: {m[0]} (PV: {m[1]})")

from ophyd.sim import motor1, motor2, det, direct_img

os.environ["no_proxy"] = "*"  # https://bugs.python.org/issue30385

print("Welcome to 3W1 at BSRF. Initializing devices...")

motors = {
    'mSampleX': motor1,
    'mSampleZ': motor2,
}

print("Initializing Eiger...")

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# eiger = Eiger("eiger_2m", "192.168.213.198", logger)
# eiger_ophyd = EigerOphyd("eiger_2m", eiger)

dets = {
    'det': det,
    'direct_img': direct_img,
#    'eiger': eiger_ophyd
}

__registered_devices = {
    DeviceType.Motor: motors,
    DeviceType.Detector: dets
}

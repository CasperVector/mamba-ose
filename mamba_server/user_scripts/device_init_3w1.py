# Beamline devices initialization script.
# =========================================
# A dictionary __registered_devices should be defined in this file.
# It is of the type: Dict[DeviceType, Dict[str, Any]]
# The _Any_ here is actually the device object. It can be a ophyd object,
# or other objects providing similar interface as an ohpyd.

from typing import Dict, Any

from . import DeviceType
from ophyd import EpicsMotor

__registered_devices: Dict[DeviceType, Dict[str, Any]]

motors = {
    'slitsH': EpicsMotor('BL3W1:stage_slits', name='motorH'),
    'slitsV': EpicsMotor('BL3W1:stage_slits', name='motorV'),
    'sampleX': EpicsMotor('BL3W1:stage_sample', name='motorX'),
    'sampleZ': EpicsMotor('BL3W1:stage_sample', name='motorZ'),
    'sampleRoll': EpicsMotor('BL3W1:stage_sample', name='motorRoll'),
    'samplePitch': EpicsMotor('BL3W1:stage_sample', name='motorPitch'),
    'detX': EpicsMotor('BL3W1:stage_detector', name='motorX'),
    'detY': EpicsMotor('BL3W1:stage_detector', name='motorY'),
    'detZ': EpicsMotor('BL3W1:stage_detector', name='motorZ'),
    'sampleR': EpicsMotor('BL3W1:sample', name='rotation'),
    'sample0': EpicsMotor('BL3W1:sample', name='sample0'),
    'sample90': EpicsMotor('BL3W1:sample', name='sample90'),
}

#
from ophyd.sim import motor1, motor2, det, direct_img
#
# motors = {
#     'mSampleX': motor1,
#     'mSampleZ': motor2,
# }

dets = {
    'det': det,
    'direct_img': direct_img
}

__registered_devices = {
    DeviceType.Motor: motors,
    DeviceType.Detector: dets
}

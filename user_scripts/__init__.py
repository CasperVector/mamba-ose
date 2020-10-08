import MambaICE

# Import types
if hasattr(MambaICE, 'DeviceType'):
    from MambaICE import DeviceType
else:
    from enum import Enum

    class DeviceType(Enum):
        Motor = 1
        Detector = 2

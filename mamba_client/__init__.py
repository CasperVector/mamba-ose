import MambaICE
from .widgets.ui import rc_icons

logger = None
config = None
mnc = None

session = None
device_manager = None
data_client = None
scan_manager = None


if hasattr(MambaICE.Dashboard, 'DeviceManagerPrx') and \
        hasattr(MambaICE.Dashboard, 'ScanManagerPrx') and \
        hasattr(MambaICE.Dashboard, 'SessionManagerPrx'):
        from MambaICE.Dashboard import (DeviceManagerPrx, ScanManagerPrx, SessionManagerPrx)
else:
    from MambaICE.dashboard_ice import (DeviceManagerPrx, ScanManagerPrx, SessionManagerPrx)

if hasattr(MambaICE, 'DeviceType') and hasattr(MambaICE, 'DataType') and \
        hasattr(MambaICE, 'TypedDataFrame') and \
        hasattr(MambaICE, 'DataDescriptor') and \
        hasattr(MambaICE, 'DeviceEntry')\
        :
    from MambaICE import (DeviceType, DataType, TypedDataFrame, DataDescriptor,
                          DeviceEntry)
else:
    from MambaICE.types_ice import (DeviceType, DataType, TypedDataFrame,
                                    DataDescriptor, DeviceEntry)

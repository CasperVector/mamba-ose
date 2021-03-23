import MambaICE
from .widgets.ui import rc_icons

logger = None
config = None

if hasattr(MambaICE.Dashboard, 'DeviceManagerPrx') and \
        hasattr(MambaICE.Dashboard, 'ScanManagerPrx'):
        from MambaICE.Dashboard import (DeviceManagerPrx, ScanManagerPrx)
else:
    from MambaICE.dashboard_ice import (DeviceManagerPrx, ScanManagerPrx)

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

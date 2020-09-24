import MambaICE
from .widgets.ui import rc_icons

logger = None
config = None

credentials = ("", "")
session = None

terminal_host = None
device_manager = None

client_adapter = None
data_client = None


if hasattr(MambaICE.Dashboard, 'DeviceManagerPrx') and \
    hasattr(MambaICE.Dashboard, 'DataClient') and \
    hasattr(MambaICE.Dashboard, 'DataRouterPrx') and \
    hasattr(MambaICE.Dashboard, 'DataClientPrx') and \
    hasattr(MambaICE.Dashboard, 'TerminalHostPrx') and\
    hasattr(MambaICE.Dashboard, 'SessionManagerPrx')\
    :
        from MambaICE.Dashboard import (DeviceManagerPrx, DataClient,
                                        DataRouterPrx, DataClientPrx,
                                        TerminalHostPrx, SessionManagerPrx)
else:
    from MambaICE.dashboard_ice import (DeviceManagerPrx, DataClient,
                                        DataRouterPrx, DataClientPrx,
                                        TerminalHostPrx, SessionManagerPrx)

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

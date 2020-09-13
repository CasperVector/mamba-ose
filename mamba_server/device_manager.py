from functools import wraps

import Ice
import MambaICE

if hasattr(MambaICE.Dashboard, 'DeviceManager') and \
        hasattr(MambaICE.Dashboard, 'UnauthorizedError'):
    from MambaICE.Dashboard import DeviceManager, UnauthorizedError
else:
    from MambaICE.dashboard_ice import DeviceManager, UnauthorizedError

import mamba_server

client_verify = mamba_server.verify


def terminal_verify(f):
    """decorator"""
    @wraps(f)
    def wrapper(self, *args):
        current = args[-1]
        if mamba_server.terminal_con == current.con:
            f(self, *args)
        else:
            raise UnauthorizedError()

    return wrapper


class DeviceManagerI(DeviceManager):
    def __init__(self):
        self.devices = {}

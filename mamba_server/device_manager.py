import struct
from functools import wraps
from typing import List

import MambaICE

if hasattr(MambaICE.Dashboard, 'DeviceManager') and \
        hasattr(MambaICE.Dashboard, 'UnauthorizedError'):
    from MambaICE.Dashboard import DeviceManager, UnauthorizedError
else:
    from MambaICE.dashboard_ice import DeviceManager, UnauthorizedError

if hasattr(MambaICE, 'DeviceType') and hasattr(MambaICE, 'DataType') and \
        hasattr(MambaICE, 'TypedDataFrame') and \
        hasattr(MambaICE, 'DataDescriptor') and \
        hasattr(MambaICE, 'DeviceEntry'):
    from MambaICE import (DeviceType, DataType, TypedDataFrame,
                          DeviceEntry)
else:
    from MambaICE.types_ice import (DeviceType, DataType, TypedDataFrame,
                                    DeviceEntry)

if hasattr(MambaICE.Experiment, 'DeviceQueryPrx'):
    from MambaICE.Experiment import DeviceQueryPrx
else:
    from MambaICE.experiment_ice import DeviceQueryPrx

import mamba_server
from utils import general_utils
from utils.data_utils import data_frame_to_value

client_verify = mamba_server.verify


def terminal_verify(f):
    """decorator"""
    @wraps(f)
    def wrapper(self, *args):
        current = args[-1]
        if mamba_server.terminal_con == current.con:
            return f(self, *args)
        else:
            raise UnauthorizedError()

    return wrapper


class DeviceManagerI(dict, DeviceManager):
    def __init__(self, communicator, host_ice_endpoint, terminal):
        super().__init__(self)
        self.logger = mamba_server.logger
        self.device_type_lookup = {}
        self._host = None
        self.communicator = communicator
        self.host_ice_endpoint = host_ice_endpoint
        self.terminal = terminal

    @property
    def host(self) -> DeviceQueryPrx:
        if self._host is None:
            self._host = DeviceQueryPrx.checkedCast(
                self.communicator.stringToProxy(
                    f"DeviceQuery:{self.host_ice_endpoint}")
            )
            self.logger.info("Create proxy to DeviceQuery.")
        return self._host

    @terminal_verify
    def addDevices(self, entries: List[DeviceEntry], current=None):
        """ICE function"""
        self.logger.info("Received device list from experiment subproc:")
        self.logger.info(entries)
        for entry in entries:
            self[entry.name] = entry
            self.device_type_lookup[entry.name] = entry.type

    @client_verify
    def listDevices(self, current=None):
        """ICE function"""
        return list(self.values())

    @client_verify
    def getDevicesByType(self, _type: DeviceType, current=None) -> List[DeviceEntry]:
        """ICE function"""
        dev_list = []
        for name, dev_type in self.device_type_lookup.items():
            if dev_type == _type:
                dev_list.append(self[name])

        return dev_list

    @client_verify
    def getDeviceConfigurations(self, name, current=None) -> List[TypedDataFrame]:
        """ICE function"""
        if name in self:
            return self.host.getDeviceConfigurations(name)

    @client_verify
    def getDeviceReadings(self, name, current=None) -> List[TypedDataFrame]:
        """ICE function"""
        if name in self:
            return self.host.getDeviceReadings(name)

    @client_verify
    def setDeviceConfiguration(self, name, frame: TypedDataFrame, current=None):
        """ICE function"""
        device: DeviceEntry = self[name]
        type_str = None
        if device.type == DeviceType.Motor:
            type_str = 'motors'
        elif device.type == DeviceType.Detector:
            type_str = 'dets'
        config_name = frame.name

        value_type = None
        for config_item in device.configs:
            if config_item.name == frame.name:
                value_type = config_item.type

        config_val = data_frame_to_value(frame).__repr__()

        if type_str:
            command = f"{type_str}.{name}.{config_name}.set({config_val})"
            self.terminal.emitCommand(command)


def initialize(communicator, adapter, terminal):
    mamba_server.device_manager = \
        DeviceManagerI(communicator, general_utils.get_experiment_subproc_endpoint(),
                       terminal)

    adapter.add(mamba_server.device_manager,
                communicator.stringToIdentity("DeviceManager"))

    mamba_server.logger.info("DeviceManager initialized.")

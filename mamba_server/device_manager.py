import struct
from functools import wraps
from typing import List

import Ice
import MambaICE

if hasattr(MambaICE.Dashboard, 'DeviceManager') and \
        hasattr(MambaICE.Dashboard, 'DeviceManagerInternal'):
    from MambaICE.Dashboard import DeviceManager, DeviceManagerInternal
else:
    from MambaICE.dashboard_ice import DeviceManager, DeviceManagerInternal

if hasattr(MambaICE, 'DeviceType') and \
        hasattr(MambaICE, 'DeviceEntry'):
    from MambaICE import (DeviceType, DeviceEntry)
else:
    from MambaICE.types_ice import (DeviceType, DeviceEntry)

if hasattr(MambaICE.Experiment, 'DeviceQueryPrx'):
    from MambaICE.Experiment import DeviceQueryPrx
else:
    from MambaICE.experiment_ice import DeviceQueryPrx

import mamba_server
from utils.data_utils import (TypedDataFrame, DataDescriptor, DataType,
                              data_frame_to_value, data_frame_to_descriptor)

class DeviceManagerInternalI(DeviceManagerInternal):
    def __init__(self, dev_mgr):
        self.dev_mgr = dev_mgr

    def addDevices(self, entries: List[DeviceEntry], current=None):
        """ICE function"""
        self.dev_mgr.logger.info("Received device list from experiment subproc:")
        self.dev_mgr.logger.info(entries)
        for entry in entries:
            if entry.name in self.dev_mgr:
                self.dev_mgr.logger.error(f"Duplicated device name: {entry.name}")
                continue
            self.dev_mgr[entry.name] = entry
            self.dev_mgr.device_type_lookup[entry.name] = entry.type


class DeviceManagerI(dict, DeviceManager):
    def __init__(self, communicator, terminal):
        super().__init__(self)
        self.logger = mamba_server.logger
        self.device_type_lookup = {}
        self._host = None
        self.communicator = communicator
        self.terminal = terminal
        self.internal_interface = None

    @property
    def host(self) -> DeviceQueryPrx:
        if self._host is None:
            self._host = DeviceQueryPrx.checkedCast(
                self.communicator.stringToProxy(
                    f"DeviceQuery:{self.terminal.get_slave_endpoint()}")
            )
            self.logger.info("Create proxy to DeviceQuery.")
        return self._host

    def get_internal_interface(self):
        if not self.internal_interface:
            self.internal_interface = DeviceManagerInternalI(self)

        return self.internal_interface

    def listDevices(self, current=None):
        """ICE function"""
        return list(self.values())

    def getDeviceConfigurations(self, name, current=None) -> List[TypedDataFrame]:
        """ICE function"""
        if name in self:
            return self.host.getDeviceConfigurations(name)
        else:
            raise NameError(f"Unknown device {name}")

    def getDeviceReadings(self, name, current=None) -> List[TypedDataFrame]:
        """ICE function"""
        if name in self:
            return self.host.getDeviceReadings(name)
        else:
            raise NameError(f"Unknown device {name}")

    def describeDeviceReadings(self, dev_name, current=None) -> List[DataDescriptor]:
        if dev_name in self:
            return self.host.describeDeviceReadings(dev_name)
        else:
            raise NameError(f"Unknown device {dev_name}")

    def getDeviceField(self, dev_name, field_name, current=None) -> TypedDataFrame:
        if dev_name in self:
            return self.host.getDeviceFieldValue(dev_name, field_name)
        else:
            raise NameError(f"Unknown device {dev_name}")

    def setDeviceConfiguration(self, name, frame: TypedDataFrame, current=None):
        """ICE function"""
        device: DeviceEntry = self[name]
        type_str = None
        if device.type == DeviceType.Motor:
            type_str = 'motors'
        elif device.type == DeviceType.Detector:
            type_str = 'dets'
        config_name = frame.component

        config_val = data_frame_to_value(frame).__repr__()

        if type_str:
            command = f"{type_str}.{name}.{config_name}.set({config_val}).wait()"
            self.terminal.emitCommand(command)

    def setDeviceValue(self, name, frame: TypedDataFrame, current=None):
        """ICE function"""
        device: DeviceEntry = self[name]
        type_str = None
        if device.type == DeviceType.Motor:
            type_str = 'motors'
        else:
            raise TypeError(f"Device {name} is not a motor.")

        val = data_frame_to_value(frame).__repr__()

        if type_str:
            command = f"{type_str}.{name}.set({val}).wait()"
            self.terminal.emitCommand(command)


def initialize(internal_ic, public_adapter, internal_adapter, terminal):
    mamba_server.device_manager = DeviceManagerI(internal_ic, terminal)

    public_adapter.add(mamba_server.device_manager,
                       Ice.stringToIdentity("DeviceManager"))
    internal_adapter.add(mamba_server.device_manager.get_internal_interface(),
                         Ice.stringToIdentity("DeviceManagerInternal"))

    mamba_server.logger.info("DeviceManager initialized.")

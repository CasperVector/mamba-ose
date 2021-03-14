import mamba_server
import struct
from functools import wraps
from typing import List

import Ice
import MambaICE

if hasattr(MambaICE.Dashboard, 'DeviceManager'):
    from MambaICE.Dashboard import DeviceManager
else:
    from MambaICE.dashboard_ice import DeviceManager

if hasattr(MambaICE, 'DeviceType') and \
        hasattr(MambaICE, 'DeviceEntry'):
    from MambaICE import (DeviceType, DeviceEntry)
else:
    from MambaICE.types_ice import (DeviceType, DeviceEntry)

import mamba_server
from utils.data_utils import (TypedDataFrame, DataDescriptor, DataType,
                              data_frame_to_value, data_frame_to_descriptor)

class DeviceManagerI(dict, DeviceManager):
    def __init__(self, communicator):
        super().__init__(self)
        self.logger = mamba_server.logger
        self.device_type_lookup = {}
        self._host = None
        self.communicator = communicator

    @property
    def host(self):
        if self._host is None:
            self._host = mamba_server.experiment_subproc.device_query_obj
        return self._host

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
            command = f"{type_str}.{name}.{config_name}.set({config_val}).wait()\n"
            mamba_server.mrc.do_cmd(command)

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
            command = f"{type_str}.{name}.set({val}).wait()\n"
            mamba_server.mrc.do_cmd(command)

    def addDevices(self, entries: List[DeviceEntry], current=None):
        """ICE function"""
        self.logger.info("Received device list from experiment subproc:")
        self.logger.info(entries)
        for entry in entries:
            if entry.name in self:
                self.logger.error(f"Duplicated device name: {entry.name}")
                continue
            self[entry.name] = entry
            self.device_type_lookup[entry.name] = entry.type

def initialize(public_ic, public_adapter):
    mamba_server.device_manager = DeviceManagerI(public_ic)
    public_adapter.add(mamba_server.device_manager,
                       Ice.stringToIdentity("DeviceManager"))
    mamba_server.logger.info("DeviceManager initialized.")

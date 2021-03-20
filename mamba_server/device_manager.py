import mamba_server
import struct
from functools import wraps
from typing import List
from typing import List, Dict, Any
import struct

import Ice
import MambaICE
from utils.data_utils import string_to_type, to_data_frame

if hasattr(MambaICE.Dashboard, 'DeviceManager'):
    from MambaICE.Dashboard import DeviceManager
else:
    from MambaICE.dashboard_ice import DeviceManager

if hasattr(MambaICE, 'DeviceType') and \
        hasattr(MambaICE, 'DeviceEntry'):
    from MambaICE import (DeviceType, DeviceEntry)
else:
    from MambaICE.types_ice import (DeviceType, DeviceEntry)

if hasattr(MambaICE.Dashboard, 'UnknownDeviceException'):
    from MambaICE.Dashboard import UnknownDeviceException
else:
    from MambaICE.dashboard_ice import UnknownDeviceException

import mamba_server
from utils.data_utils import (TypedDataFrame, DataDescriptor, DataType,
                              data_frame_to_value, data_frame_to_descriptor)

from enum import Enum


class Kind(Enum):
    config = 0
    read = 1


class DeviceQueryI(dict):
    def __init__(self, typed_device_dict=None):
        super().__init__(self)
        self.device_type_lookup = {}
        if typed_device_dict:
            self.load_devices(typed_device_dict)

    def load_devices(self, typed_device_dict: Dict[DeviceType, Dict[str, Any]]):
        for _type, dev_dict in typed_device_dict.items():
            for name, dev in dev_dict.items():
                self[name] = dev
                self.device_type_lookup[name] = _type

    def push_devices_to_host(self, host):
        host.addDevices(self.listDevices())

    def getDeviceConfigurations(self, dev_name, current=None) -> List[TypedDataFrame]:
        """ICE function"""
        if dev_name not in self:
            raise UnknownDeviceException

        dev = self[dev_name]
        return self.get_device_fields(dev, Kind.config)

    def getDeviceReadings(self, dev_name, current=None):
        """ICE function"""
        if dev_name not in self:
            raise UnknownDeviceException

        dev = self[dev_name]
        return self.get_device_fields(dev, Kind.read)

    def describeDeviceReadings(self, dev_name, current=None):
        """ICE function"""
        if dev_name not in self:
            raise UnknownDeviceException

        dev = self[dev_name]
        return self.get_device_field_descriptions(dev, Kind.read)

    def getDeviceFieldValue(self, dev_name, component_name, current=None):
        return self.get_device_field_value(self[dev_name], component_name)

    def listDevices(self, current=None):
        """ICE function"""
        dev_list = []
        for name, dev in self.items():
            dev_list.append(
                DeviceEntry(
                    name=name,
                    type=self.device_type_lookup[name],
                    configs=self.get_device_field_descriptions(dev, Kind.config),
                    readings=self.get_device_field_descriptions(dev, Kind.read),
                )
            )

        return dev_list

    def get_device_fields(self, dev, kind) -> List[TypedDataFrame]:
        fields: List[TypedDataFrame] = []
        cpt_lists = dev.read_attrs if kind == Kind.read else dev.configuration_attrs

        for cpt_name in cpt_lists:
            cpt = self.resolve_component(dev, cpt_name)
            des = cpt.describe() if cpt else None
            if des:
                for key, field in des.items():
                    _type = string_to_type(field['dtype'])
                    if 'enum_strs' in field:
                        _type = DataType.String
                    field_val = cpt.read()[key]
                    fields.append(
                        to_data_frame(
                            key,
                            cpt_name,
                            _type,
                            field_val['value'],
                            timestamp=field_val['timestamp']
                        )
                    )

        return fields

    def get_device_field_descriptions(self, dev, kind, prefix="") -> List[DataDescriptor]:
        fields: List[DataDescriptor] = []
        cpt_lists = dev.read_attrs if kind == Kind.read else dev.configuration_attrs

        for cpt_name in cpt_lists:
            cpt = self.resolve_component(dev, cpt_name)
            des = cpt.describe() if cpt else None
            if des:
                for key, field in des.items():
                    _type = string_to_type(field['dtype'])
                    if 'enum_strs' in field:
                        _type = DataType.String
                    fields.append(
                        DataDescriptor(
                            name=key,
                            component=cpt_name,
                            type=_type,
                            shape=field['shape']
                        )
                    )

        return fields

    def resolve_component(self, dev, cpt_name):
        cpt = None
        _cpt = dev
        _name = cpt_name
        while True:
            split = _name.split(".", 1)
            if len(split) == 1:
                cpt = getattr(_cpt, split[0])
                break
            else:
                _cpt = getattr(_cpt, split[0])
                _name = split[1]

        if hasattr(cpt, "component_names"):
            return None

        return cpt

    def get_device_field_value(self, dev, cpt_name) -> TypedDataFrame:
        if "." in cpt_name:
            cpt, attr = cpt_name.split(".", 1)
            return self.get_device_field_value(getattr(dev, cpt), attr)

        cpt = getattr(dev, cpt_name)

        des = cpt.describe()
        if des:
            field = des.keys()[0]
            _type = string_to_type(field['dtype'])
            if 'enum_strs' in field:
                _type = DataType.String
            field_val = list(cpt.read().values())[0]
            return to_data_frame(
                field,
                cpt_name,
                _type,
                field_val['value'],
                timestamp=field_val['timestamp']
            )

        raise Exception("No field description found.")


class DeviceManagerI(dict, DeviceManager):
    def __init__(self):
        super().__init__(self)
        self.logger = mamba_server.logger
        self.device_type_lookup = {}
        self.host = mamba_server.device_query_obj

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

def initialize(public_adapter):
    mamba_server.device_query_obj = DeviceQueryI()
    mamba_server.device_manager = DeviceManagerI()
    public_adapter.add(mamba_server.device_manager,
                       Ice.stringToIdentity("DeviceManager"))
    mamba_server.logger.info("DeviceManager initialized.")

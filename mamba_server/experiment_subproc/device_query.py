from typing import List, Dict, Any
import struct

import MambaICE
import MambaICE.Dashboard
from utils.data_utils import string_to_type, to_data_frame

# Fool the linter. The else branch will never be executed, but leave it here
# to make linter and auto-completion work.

if hasattr(MambaICE, 'DeviceType') and hasattr(MambaICE, 'DataType') and \
        hasattr(MambaICE, 'TypedDataFrame') and \
        hasattr(MambaICE, 'DataDescriptor') and \
        hasattr(MambaICE, 'DeviceEntry'):
    from MambaICE import (DeviceType, DataType, TypedDataFrame, DataDescriptor,
                          DeviceEntry)
else:
    from MambaICE.types_ice import (DeviceType, DataType, TypedDataFrame,
                                    DataDescriptor, DeviceEntry)

if hasattr(MambaICE.Dashboard, 'UnknownDeviceException'):
    from MambaICE.Dashboard import UnknownDeviceException
else:
    from MambaICE.dashboard_ice import UnknownDeviceException

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


def initialize():
    import mamba_server.experiment_subproc
    device_query_obj = DeviceQueryI()
    mamba_server.experiment_subproc.device_query_obj = device_query_obj

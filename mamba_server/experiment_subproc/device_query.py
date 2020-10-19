from typing import List, Dict, Any
import struct

import MambaICE
import MambaICE.Experiment
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

if hasattr(MambaICE.Experiment, 'UnknownDeviceException') and \
        hasattr(MambaICE.Experiment, 'DeviceQuery'):
    from MambaICE.Experiment import UnknownDeviceException, DeviceQuery
else:
    from MambaICE.experiment_ice import UnknownDeviceException, DeviceQuery

from enum import Enum


class Kind(Enum):
    config = 0
    read = 1


class DeviceQueryI(dict, DeviceQuery):
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

    def getDevicesByType(self, _type, current=None) -> List[DeviceEntry]:
        """ICE function"""
        dev_list = []
        for name, dev in self.items():
            if self.device_type_lookup[name] == _type:
                dev_list.append(
                    DeviceEntry(
                        name=name,
                        type=self.device_type_lookup[name],
                        configs=self.get_device_field_descriptions(dev, Kind.config),
                        readings=self.get_device_field_descriptions(dev, Kind.hinted)
                    )
                )

        return dev_list

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
        return self.get_device_fields(dev, Kind.normal)

    def getDeviceHintedReadings(self, dev_name, current=None):
        """ICE function"""
        if dev_name not in self:
            raise UnknownDeviceException

        dev = self[dev_name]
        return self.get_device_fields(dev, Kind.hinted)

    def getDeviceFieldValue(self, dev_name, field_name, current=None):
        return self.get_device_field_value(self[dev_name], field_name)

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
            des = list(cpt.describe().values())
            if des:
                field = des[0]
                _type = string_to_type(field['dtype'])
                if 'enum_strs' in field:
                    _type = DataType.String
                field_val = list(cpt.read().values())[0]
                fields.append(
                    to_data_frame(
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
            des = list(cpt.describe().values())
            if des:
                field = des[0]
                _type = string_to_type(field['dtype'])
                if 'enum_strs' in field:
                    _type = DataType.String
                fields.append(
                    DataDescriptor(
                        name=cpt_name,
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
                cpt = getattr(dev, split[0])
                break
            else:
                _cpt = getattr(dev, split[0])
                _name = split[1]

        return cpt

    def get_device_field_value(self, dev, field_name) -> TypedDataFrame:
        if "." in field_name:
            cpt, attr = field_name.split(".", 1)
            return self.get_device_field_value(getattr(dev, cpt), attr)

        cpt = getattr(dev, field_name)

        des = list(cpt.describe().values())
        if des:
            field = des[0]
            _type = string_to_type(field['dtype'])
            if 'enum_strs' in field:
                _type = DataType.String
            field_val = list(cpt.read().values())[0]
            return to_data_frame(
                field_name,
                _type,
                field_val['value'],
                timestamp=field_val['timestamp']
            )

        raise Exception("No field description found.")


def initialize(communicator, adapter):
    import mamba_server.experiment_subproc
    device_query_obj = DeviceQueryI()
    adapter.add(device_query_obj,
                communicator.stringToIdentity("DeviceQuery"))

    mamba_server.experiment_subproc.device_query_obj = device_query_obj

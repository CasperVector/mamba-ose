import struct
from datetime import datetime

from mamba_client import (DataDescriptor, DataFrame, DataType,
                          DataClient, DataRouterPrx, DataClientPrx)

import mamba_client


class DataClientI(DataClient):
    def __init__(self, communicator, ice_endpoint, logger):
        super().__init__()

        self.logger = logger
        self.communicator = communicator
        self.host = DataRouterPrx.checkedCast(
            communicator.stringToProxy(f"DataRouter:{ice_endpoint}")
                        .ice_connectionId("MambaClient")
        )

        self.scan_id = 0
        self.data_descriptors = {}
        self.data_callbacks = {}

        self.register_client_instance()

    def register_client_instance(self):
        if mamba_client.client_adapter is None:
            mamba_client.client_adapter = self.communicator.createObjectAdapter("")
            self.host.ice_getConnection().setAdapter(mamba_client.client_adapter)
            mamba_client.client_adapter.activate()

        proxy = DataClientPrx.uncheckedCast(
            mamba_client.client_adapter.addWithUUID(self))

        self.host.registerClient(proxy)

    def request_data(self, name, callback):
        if name not in self.data_callbacks:
            self.data_callbacks[name] = [callback]
            self.host.subscribe(list(self.data_callbacks.keys()))
        else:
            self.data_callback[name].append(callback)

    def data_callback_invoke(self, name, *args):
        if name in self.data_callbacks:
            for cb in self.data_callbacks[name]:
                self.logger.info(f"Invoking callback {cb}")
                cb(*args)

    def scanStart(self, id, descriptors, current):
        self.scan_id = id
        if len(descriptors) > 0:
            for key, des in descriptors.items():
                assert isinstance(des, DataDescriptor)
                self.data_descriptors[des.name] = des
                self.data_callback_invoke(des.name, None, None)

    def dataUpdate(self, frames, current):
        for frame in frames:
            assert isinstance(frame, DataFrame)
            value = self._to_value(frame.value,
                                   self.data_descriptors[frame.name].type)
            timestamp = datetime.fromtimestamp(frame.timestamp)
            self.data_callback_invoke(frame.name, value, timestamp)

    def scanEnd(self, status, current):
        pass

    @staticmethod
    def _to_value(value, _type):
        assert isinstance(_type, DataType)
        if _type == DataType.Float:
            return struct.unpack("d", value)[0]
        elif _type == DataType.Integer:
            return struct.unpack("i", value)[0]
        elif _type == DataType.String:
            return value.decode("utf-8")

        return None

import struct
from datetime import datetime

from mamba_client import (DataDescriptor, DataType,
                          DataClient, DataRouterPrx, DataClientPrx)

import mamba_client
from utils.data_utils import data_frame_to_value


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

    def request_data(self, data_name, callback):
        if data_name not in self.data_callbacks:
            self.data_callbacks[data_name] = [callback]
            self.host.subscribe(list(self.data_callbacks.keys()))
        else:
            self.data_callback[data_name].append(callback)

    def stop_requesting_data(self, _callback):
        data_to_unregister = []
        for name, callbacks in self.data_callbacks.items():
            if _callback in callbacks:
                self.data_callbacks[name].remove(_callback)
                if not self.data_callbacks[name]:
                    data_to_unregister.append(name)

        for data in data_to_unregister:
            del self.data_callbacks[data]
        self.host.unsubscribe(data_to_unregister)

    def data_callback_invoke(self, name, *args):
        if name in self.data_callbacks:
            for cb in self.data_callbacks[name]:
                self.logger.info(f"Invoking callback {cb}")
                cb(*args)
        elif name == "*":
            for name, cbks in self.data_callbacks.items():
                for cb in cbks:
                    self.logger.info(f"Invoking callback {cb}")
                    cb(*args)

    def scanStart(self, id, descriptors, current):
        self.scan_id = id
        self.logger.info("Received scan started message. Data to be received: "
                         + str([des.name for des in descriptors]))
        if len(descriptors) > 0:
            for des in descriptors:
                assert isinstance(des, DataDescriptor)
                self.data_descriptors[des.name] = des
                self.data_callback_invoke(des.name, None, None)
                print(des.name)

    def dataUpdate(self, frames, current):
        self.logger.info("Received data frames: " +
                         str([frame.name for frame in frames]))
        for frame in frames:
            value = data_frame_to_value(frame)
            timestamp = datetime.fromtimestamp(frame.timestamp)
            self.data_callback_invoke(frame.name, value, timestamp)

    def scanEnd(self, status, current):
        self.data_callback_invoke("*", None, None)

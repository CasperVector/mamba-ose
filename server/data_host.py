import struct

import Ice
from Dashboard import DataHost, DataDescriptor, DataFrame, DataType, \
    ScanExitStatus

from bluesky.callbacks.core import CallbackBase, make_class_safe

import server

client_verify = server.verify


class DataHostI(DataHost):
    def __init__(self, logger):
        self.logger = logger
        self.clients = []
        self.subscription = {}
        self.keys = []
        self.scan_id = 0

    @client_verify
    def registerClient(self, client: DataClient, current):
        self.logger.info("Data client connected: "
                         + Ice.identityToString(client.ice_getIdentity()))
        self.clients.append(client.ice_fixed(current.con))
        current.con.setCloseCallback(
            lambda conn: self._connection_closed_callback(client))

    def start_scan(self, _id):
        self.scan_id = _id

    def send_descriptor(self, keys):
        self.keys = keys

        for client in self.clients:
            to_send = []
            for key, des in keys:
                if key in self.subscription[client] or \
                        "*" in self.subscription[client]:
                    to_send.append(des)
            try:
                client.scanStart(self.scan_id, to_send)
            except Ice.CloseConnectionException:
                self._connection_closed_callback(client)

    def send_data_frame(self, frames):
        for client in self.clients:
            to_send = []
            for key, frame in frames:
                if key in self.subscription[client] or \
                        "*" in self.subscription[client]:
                    to_send.append(frame)
            try:
                client.dataUpdate(to_send)
            except Ice.CloseConnectionException:
                self._connection_closed_callback(client)

    def end_scan(self, status):
        for client in self.clients:
            try:
                client.scanEnd(status)
            except Ice.CloseConnectionException:
                self._connection_closed_callback(client)

    def _connection_closed_callback(self, client):
        self.logger.info("Lost connection with client: " +
                         Ice.identityToString(client.ice_getIdentity())
                         )
        self.clients.remove(client)


@make_class_safe(logger=server.logger)
class DataDispatchCallback(CallbackBase):
    def __init__(self, data_host: DataHostI, logger):
        self.logger = logger
        self.data_host = data_host
        self.data_keys = {}

    def start(self, doc):
        self.logger.info(
            f"Received scan start event. Scan ID: {doc['scan_id']}")
        self.data_host.start_scan(doc['scan_id'])

    def descriptor(self, doc):
        # TODO: process header, scan metadata, etc
        self.logger.info("Received scan descriptor.")

        self.data_keys = keys = list(doc['data_keys'])

        data_descriptors = {
            keys: DataDescriptor(key,
                                 self._to_type(des['dtype']),
                                 des['shape']) for key, des in keys
        }

        self.data_host.send_descriptor(data_descriptors)

    def event(self, doc):
        data_frames = {
            key: DataFrame(key,
                           self._pack(self.data_keys[key]['dtype'], num),
                           doc['timestamps'][key]) for key, num in doc['data']
        }

        self.data_host.send_data_frame(data_frames)

    def stop(self, doc):
        if doc['exit_status'] == 'success':
            self.data_host.end_scan(ScanExitStatus.Success)
        elif doc['exit_status'] == 'abort':
            self.data_host.end_scan(ScanExitStatus.Abort)
        elif doc['exit_status'] == 'fail':
            self.data_host.end_scan(ScanExitStatus.Fail)

    @staticmethod
    def _to_type(string):
        if string == 'number':
            return DataType.Float
        elif string == 'string':
            return DataType.String

    @staticmethod
    def _pack(type, value):
        if type == 'number':
            return struct.pack("d", float(value))
        elif type == 'string':
            return value.encode('utf-8')

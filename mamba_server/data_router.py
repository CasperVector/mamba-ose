from typing import List
from functools import wraps
from collections import namedtuple
from abc import ABC
from bluesky.callbacks.core import CallbackBase, make_class_safe

import Ice
import IcePy
from MambaICE import (DataType, DataDescriptor, TypedDataFrame, StringDataFrame,
                      FloatDataFrame, IntegerDataFrame, ArrayDataFrame)
from MambaICE.Dashboard import DataRouter, DataRouterRecv, DataClient, ScanExitStatus
from utils.data_utils import DataDescriptor, TypedDataFrame
from utils.data_utils import string_to_type, to_data_frame
from mamba_server.session_manager import set_connection_closed_callback

import mamba_server

Client = namedtuple("Client", ["is_remote", "prx", "callback"])
# is_remote: bool, specify the client is Remote or Local.
# prx: DataClientPrx, for remote client.
# callback: DataClientCallback, if the client is local, this is the callback
#  interface to invoke.


class DataClientCallback(ABC):
    def scan_start(self, _id, data_descriptors):
        raise NotImplementedError

    def data_update(self, frames):
        raise NotImplementedError

    def scan_end(self, status):
        raise NotImplementedError


class DataRouterRecvI(DataRouterRecv):
    def __init__(self, data_router):
        self.data_router = data_router

    def scanStart(self, _id, keys, current=None):
        self.data_router.logger.info(f"Scan start received, scan id {_id}")
        self.data_router.scan_id = _id

        # forward data
        for client in self.data_router.clients:
            to_send = []
            for key in keys:
                self.data_router.keys[key.name] = key
                if client not in self.data_router.subscription:
                    continue
                if key.name in self.data_router.subscription[client] or \
                        ("*" in self.data_router.subscription[client] and
                         not key.name.startswith("__")):
                    to_send.append(key)
            try:
                self.data_router.logger.info(f"Forward data descriptors to {client}")
                if client.is_remote:
                    client.prx.scanStart(self.data_router.scan_id, to_send)
                else:
                    client.callback.scan_start(self.data_router.scan_id, to_send)
            except Ice.ConnectionLostException:
                self.data_router._connection_closed_callback(current.con)
                pass

    def pushData(self, frames, current=None):
        for client in self.data_router.clients:
            to_send = []
            for frame in frames:
                key = frame.name
                if key in self.data_router.subscription[client] or \
                        ("*" in self.data_router.subscription[client] and
                         not key.startswith("__")):
                    to_send.append(frame)
            if to_send:
                try:
                    names = [frame.name for frame in frames]
                    self.data_router.logger.info(f"Forward data frames {names} to {client}")
                    if client.is_remote:
                        client.prx.dataUpdate(to_send)
                    else:
                        client.callback.data_update(to_send)
                except (Ice.ConnectionLostException):
                    self.data_router._connection_closed_callback(current.con)

    def scanEnd(self, status, current):
        self.data_router.logger.info(f"Scan end received")
        for client in self.data_router.clients:
            try:
                if client.is_remote:
                    client.prx.scanEnd(status)
                else:
                    client.callback.scan_end(status)
            except Ice.CloseConnectionException:
                self.data_router._connection_closed_callback(current.con)


class DataRouterI(DataRouter):
    def __init__(self):
        self.logger = mamba_server.logger
        self.clients = []
        self.local_clients = {}
        self.conn_to_client = {}
        self.subscription = {}
        self.keys = {}
        self.scan_id = 0
        self.recv_interface = None

    def registerClient(self, client: DataClient, current=None):
        self.logger.info("Remote data client connected: "
                         + Ice.identityToString(client.ice_getIdentity()))
        client_prx = client.ice_fixed(current.con)
        client = Client(True, client_prx, None)
        self.clients.append(client)
        self.conn_to_client[current.con] = client
        self.subscription[client] = []
        set_connection_closed_callback(
            current.con,
            self._connection_closed_callback
        )

    def local_register_client(self, name, callback: DataClientCallback):
        self.logger.info(f"Local data client registered: {name}")
        client = Client(False, None, callback)
        self.clients.append(client)
        self.local_clients[name] = client
        self.subscription[client] = []

    def subscribe(self, items, current=None):
        client = self.conn_to_client[current.con]
        self.subscription[client] = items

    def subscribeAll(self, current=None):
        client = self.conn_to_client[current.con]
        self.subscription[client] = ["*"]

    def unsubscribe(self, items, current=None):
        client = self.conn_to_client[current.con]
        for item in items:
            try:
                self.subscription[client].remove(item)
            except ValueError:
                pass

    def local_subscribe(self, name, items):
        client = self.local_clients[name]
        self.subscription[client] = items

    def local_subscribe_all(self, name):
        client = self.local_clients[name]
        self.subscription[client] = ["*"]

    def get_recv_interface(self):
        if not self.recv_interface:
            self.recv_interface = DataRouterRecvI(self)

        return self.recv_interface

    def _connection_closed_callback(self, conn):
        client = self.conn_to_client[conn]
        self.clients.remove(client)
        del self.subscription[client]
        conn_to_delete = None
        for conn, _client in self.conn_to_client.items():
            if _client == client:
                conn_to_delete = conn
                break
        del self.conn_to_client[conn_to_delete]


class DataDispatchCallback(CallbackBase):
    def __init__(self, data_host):
        super().__init__()
        self.data_host = data_host
        self.data_keys = {}
        self.scan_id = 0

    def start(self, doc):
        self.scan_id = doc['scan_id']

    def descriptor(self, doc):
        # TODO: process header, scan metadata, etc

        self.data_keys = keys = doc['data_keys']

        for key in keys.keys():
            keys[key]['dtype'] = string_to_type(keys[key]['dtype'])

        data_descriptors = [
            DataDescriptor(key,
                           "",
                           des['dtype'],
                           des['shape']) for key, des in keys.items()
        ]
        self.data_host.scanStart(self.scan_id, data_descriptors)

    def event(self, doc):
        data_frames = []
        for key, value in doc['data'].items():
            if 'external' in self.data_keys[key]:
                continue
            data_frames.append(
                to_data_frame(
                    key,
                    "",
                    self.data_keys[key]['dtype'],
                    value,
                    doc['timestamps'][key])
            )

        self.data_host.pushData(data_frames)

    def stop(self, doc):
        if doc['exit_status'] == 'success':
            self.data_host.scanEnd(ScanExitStatus.Success)
        elif doc['exit_status'] == 'abort':
            self.data_host.scanEnd(ScanExitStatus.Abort)
        elif doc['exit_status'] == 'fail':
            self.data_host.scanEnd(ScanExitStatus.Fail)


def initialize(public_adapter):
    mamba_server.data_router = DataRouterI()
    mamba_server.data_callback = DataDispatchCallback(mamba_server.data_router)
    public_adapter.add(mamba_server.data_router,
                       Ice.stringToIdentity("DataRouter"))
    public_adapter.add(mamba_server.data_router.get_recv_interface(),
                         Ice.stringToIdentity("DataRouterRecv"))
    mamba_server.logger.info("DataRouter initialized.")


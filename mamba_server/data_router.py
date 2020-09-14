from functools import wraps

import Ice
from MambaICE.Dashboard import DataRouter, DataClient, UnauthorizedError

import mamba_server

client_verify = mamba_server.verify


def terminal_verify(f):
    """decorator"""
    @wraps(f)
    def wrapper(self, *args):
        current = args[-1]
        if mamba_server.terminal_con == current.con:
            f(self, *args)
        else:
            raise UnauthorizedError()

    return wrapper


class DataRouterI(DataRouter):
    def __init__(self):
        self.logger = mamba_server.logger
        self.clients = []
        self.conn_to_client = {}
        self.subscription = {}
        self.keys = {}
        self.scan_id = 0

    @client_verify
    def registerClient(self, client: DataClient, current):
        self.logger.info("Data mamba_client connected: "
                         + Ice.identityToString(client.ice_getIdentity()))
        client = client.ice_fixed(current.con)
        self.clients.append(client)
        self.conn_to_client[current.con] = client
        self.subscription[client] = []
        current.con.setCloseCallback(
            lambda conn: self._connection_closed_callback(client))

    @client_verify
    def subscribe(self, items, current):
        client = self.conn_to_client[current.con]
        self.subscription[client] = items

    @client_verify
    def subscribeAll(self, current):
        client = self.conn_to_client[current.con]
        self.subscription[client] = ["*"]

    @terminal_verify
    def scanStart(self, id, keys, current):
        self.logger.info(f"Scan start received, scan id {id}")
        self.scan_id = id

        # forward data
        for client in self.clients:
            to_send = {}
            for key in keys:
                self.keys[key.name] = key
                if client not in self.subscription:
                    continue
                if key.name in self.subscription[client] or \
                        "*" in self.subscription[client]:
                    to_send[key.name] = key
            try:
                self.logger.info(f"Forward data descriptors to {client}")
                client.scanStart(self.scan_id, to_send)
            except Ice.CloseConnectionException:
                self._connection_closed_callback(client)
                pass

    @terminal_verify
    def pushData(self, frames, current):
        self.logger.info(f"Data frames received from bluesky callback")
        for client in self.clients:
            to_send = []
            for frame in frames:
                key = frame.name
                if key in self.subscription[client] or \
                        "*" in self.subscription[client]:
                    to_send.append(frame)
            if to_send:
                try:
                    self.logger.info(f"Forward data frames to {client}")
                    client.dataUpdate(to_send)
                except Ice.CloseConnectionException:
                    self._connection_closed_callback(client)

    @terminal_verify
    def scanEnd(self, status, current):
        self.logger.info(f"Scan end received")
        for client in self.clients:
            try:
                client.scanEnd(status)
            except Ice.CloseConnectionException:
                self._connection_closed_callback(client)

    def _connection_closed_callback(self, client):
        self.logger.info("Lost connection with mamba_client: " +
                         Ice.identityToString(client.ice_getIdentity())
                         )
        self.clients.remove(client)
        del self.subscription[client]
        conn_to_delete = None
        for conn, _client in self.conn_to_client.items():
            if _client == client:
                conn_to_delete = conn
                break
        del self.conn_to_client[conn_to_delete]


def initialize(communicator, adapter):
    mamba_server.data_router = DataRouterI()

    adapter.add(mamba_server.data_router,
                communicator.stringToIdentity("DataRouter"))

    mamba_server.logger.info("DataHost initialized.")

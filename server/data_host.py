import Ice
import Dashboard

from bluesky.callbacks.core import CallbackBase

import server

client_verify = server.verify


class DataHostI(Dashboard.DataHost):
    def __init__(self, logger):
        self.logger = logger
        self.clients = []

    @client_verify
    def registerClient(self, client: Dashboard.DataClient, current):
        self.logger.info("Data client connected: "
                         + Ice.identityToString(client.ice_getIdentity()))
        self.clients.append(client.ice_fixed(current.con))

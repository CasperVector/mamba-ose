import Dashboard

from pyqterm import Terminal

import client


class TerminalWidget(Terminal, Dashboard.TerminalClient):
    def __init__(self, communicator, ice_endpoint, logger):
        super().__init__(400, 250, logger=logger)

        self.communicator = communicator
        self.host = Dashboard.TerminalHostPrx.checkedCast(
            communicator.stringToProxy(f"TerminalHost:{ice_endpoint}"))
        self.register_client_instance()

        self.stdin_callback = self.host.stdin
        self.resize_callback = self.host.resize

        self.resize(400, 250)

    def register_client_instance(self):
        if client.client_adapter is None:
            client.client_adapter = self.communicator.createObjectAdapter("")
            self.host.ice_getConnection().setAdapter(client.client_adapter)
            client.client_adapter.activate()

        proxy = Dashboard.TerminalClientPrx.uncheckedCast(
            client.client_adapter.addWithUUID(self))

        self.host.registerClient(proxy)

    def stdout(self, s, current):
        super().stdout(s)

    @classmethod
    def get_init_func(cls, communciator, ice_endpoint, logger):
        return lambda: cls(communciator, ice_endpoint, logger)

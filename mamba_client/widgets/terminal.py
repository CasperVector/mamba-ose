import MambaICE.Dashboard as Dashboard

from pyqterm import Terminal

import mamba_client


class TerminalWidget(Terminal, Dashboard.TerminalClient):
    def __init__(self, communicator, terminal_host, logger):
        super().__init__(400, 250, logger=logger)

        self.communicator = communicator
        self.host = terminal_host
        self.register_client_instance()

        self.stdin_callback = self.host.stdin
        self.resize_callback = self.host.resize

        self.resize(400, 250)

    def register_client_instance(self):
        if mamba_client.client_adapter is None:
            mamba_client.client_adapter = self.communicator.createObjectAdapter("")
            self.host.ice_getConnection().setAdapter(mamba_client.client_adapter)
            mamba_client.client_adapter.activate()

        proxy = Dashboard.TerminalClientPrx.uncheckedCast(
            mamba_client.client_adapter.addWithUUID(self))

        self.host.registerClient(proxy)

    def stdout(self, s, current):
        super().stdout(s)

    @classmethod
    def get_init_func(cls, communciator, terminal_host, logger):
        return lambda: cls(communciator, terminal_host, logger)

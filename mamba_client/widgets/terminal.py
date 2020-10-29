import MambaICE.Dashboard as Dashboard

from termqt import Terminal
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QScrollBar
from PyQt5.QtCore import Qt

import mamba_client


class TerminalWidget(QWidget, Dashboard.TerminalClient):
    def __init__(self, communicator, terminal_host, logger):
        super().__init__()
        self.terminal_widget = Terminal(400, 250, logger=logger)

        self.communicator = communicator
        self.host = terminal_host
        self.register_client_instance()

        self.terminal_widget.stdin_callback = self.host.stdin
        self.terminal_widget.resize_callback = self.host.resize

        self.scroll_bar = QScrollBar(Qt.Vertical, self)
        self.terminal_widget.connect_scroll_bar(self.scroll_bar)

        self.layout = QHBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.terminal_widget)
        self.layout.addWidget(self.scroll_bar)
        self.setLayout(self.layout)

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
        self.terminal_widget.stdout(s)

    @classmethod
    def get_init_func(cls, communciator, terminal_host, logger):
        return lambda: cls(communciator, terminal_host, logger)

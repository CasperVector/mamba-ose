import threading

import Ice
from MambaICE.Dashboard import (TerminalHost, TerminalEventHandler)
import mamba_server
from utils import general_utils
from termqt import TerminalBuffer
from mamba_server.experiment_subproc.subprocess_spawn import IPythonTerminalIO
from mamba_server.session_manager import set_connection_closed_callback

class TerminalHostI(TerminalHost):
    def __init__(self, event_hdl: 'TerminalEventHandlerI'):
        self._terminal = None
        self.logger = mamba_server.logger
        self.event_hdl = event_hdl
        self.terminal_buffer = TerminalBuffer(80, 24, self.logger)
        self.spawn()

    @property
    def terminal(self):
        if not self._terminal:
            self.spawn()
        return self._terminal

    def spawn(self):
        if not self._terminal:
            access_endpoint = general_utils.get_internal_endpoint()
            print(access_endpoint)

            self._terminal = IPythonTerminalIO(80, 24,
                                               access_endpoint,
                                               self.logger)

            self._terminal.stdout_callback = self.terminal_buffer.stdout
            self._terminal.terminated_callback = self._terminated_callback
            self.terminal_buffer.stdin_callback = self.terminal.write
            self._terminal.spawn()
            self.logger.info("Terminal thread spawned, waiting for event "
                             "emitters to attach.")

    def emitCommand(self, cmd, current=None):
        self.terminal.write(b'\x15' + cmd.encode('utf-8') + b'\r')

    def get_slave_endpoint(self):
        return general_utils.format_endpoint("127.0.0.1",
                                             self.event_hdl.slave_port,
                                             "tcp")

    def _terminated_callback(self):
        self._terminal = None


class TerminalEventHandlerI(TerminalEventHandler):
    def __init__(self):
        self.slave_port = 0

    def attach(self, port, current):
        self.slave_port = port
        self.logger.info(f"Terminal event emitter attached, binding at {port}.")


def initialize(public_adapter, internal_adapter):
    event_hdl = TerminalEventHandlerI()
    mamba_server.terminal = TerminalHostI(event_hdl)

    public_adapter.add(mamba_server.terminal,
                       Ice.stringToIdentity("TerminalHost"))
    internal_adapter.add(event_hdl,
                         Ice.stringToIdentity("TerminalEventHandler"))
    mamba_server.logger.info("TerminalHost, TerminalEventHandler initialized.")

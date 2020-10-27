from functools import wraps
import threading

import Ice
from MambaICE.Dashboard import (TerminalHost, TerminalClientPrx, UnauthorizedError,
                                TerminalEventHandler)
import mamba_server
from utils import general_utils
from termqt import TerminalBuffer
from mamba_server.experiment_subproc.subprocess_spawn import IPythonTerminalIO
from mamba_server.session_manager import set_connection_closed_callback

client_verify = mamba_server.verify


class TerminalHostI(TerminalHost):
    def __init__(self, event_hdl: 'TerminalEventHandlerI'):
        self._terminal = None
        self.clients = []
        self.conn_to_client = {}
        self.logger = mamba_server.logger
        self.event_hdl = event_hdl
        self.terminal_buffer = TerminalBuffer(80, 24, self.logger)
        self.spawn()

    @client_verify
    def registerClient(self, client: TerminalClientPrx, current):
        self.logger.info("Terminal mamba_client connected: "
                         + Ice.identityToString(client.ice_getIdentity()))
        client = client.ice_fixed(current.con)
        self.clients.append(client)
        self.conn_to_client[current.con] = client
        set_connection_closed_callback(current.con,
                                       self._connection_closed_callback)

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

            self._terminal.stdout_callback = self._stdout_callback
            self._terminal.terminated_callback = self._terminated_callback
            self.terminal_buffer.stdin_callback = self.terminal.write
            self._terminal.spawn()
            self.logger.info("Terminal thread spawned, waiting for event "
                             "emitters to attach.")

    @client_verify
    def emitCommand(self, cmd, current=None):
        self.event_hdl.idle.wait()
        self.terminal.write(b'\x15' + cmd.encode('utf-8') + b'\r')

    @client_verify
    def stdin(self, s: bytes, current=None):
        self.terminal.write(s)

    @client_verify
    def resize(self, rows, cols, current):
        self.terminal_buffer.resize(rows, cols)
        self.terminal.resize(rows, cols)

    def _stdout_callback(self, s):
        self.terminal_buffer.stdout(s)
        for client in self.clients:
            try:
                client.stdout(s)
            except Ice.ConnectionLostException:
                pass

    def get_slave_endpoint(self):
        return general_utils.format_endpoint("127.0.0.1",
                                             self.event_hdl.slave_port,
                                             "tcp")

    def _connection_closed_callback(self, conn):
        self.clients.remove(self.conn_to_client[conn])

    def _terminated_callback(self):
        self.event_hdl.event_emitter_con = None
        self.event_hdl.event_token = None
        self._terminal = None
        # self.terminal.spawn()


class TerminalEventHandlerI(TerminalEventHandler):
    def __init__(self):
        self.logger = mamba_server.logger
        self.idle = threading.Event()
        self.idle.set()
        self.slave_port = 0

    # ----------------------
    #   Exposed to emitter
    # ----------------------

    def attach(self, port, current):
        self.slave_port = port
        self.logger.info(f"Terminal event emitter attached, binding at {port}.")

    def enterExecution(self, cmd, current):
        self.logger.info(f"executed {cmd}")
        self.idle.clear()

    def leaveExecution(self, result, current):
        self.logger.info(f"result {result}")
        self.idle.set()


def initialize(public_adapter, internal_adapter):
    event_hdl = TerminalEventHandlerI()
    mamba_server.terminal = TerminalHostI(event_hdl)

    public_adapter.add(mamba_server.terminal,
                       Ice.stringToIdentity("TerminalHost"))
    internal_adapter.add(event_hdl,
                         Ice.stringToIdentity("TerminalEventHandler"))

    mamba_server.logger.info("TerminalHost, TerminalEventHandler initialized.")

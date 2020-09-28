from functools import wraps
import threading

import Ice
from MambaICE.Dashboard import (TerminalHost, TerminalClientPrx, UnauthorizedError,
                                TerminalEventHandler)
import mamba_server
from utils import general_utils
from mamba_server.experiment_subproc.subprocess_spawn import IPythonTerminalIO
from mamba_server.session_manager import set_connection_closed_callback

client_verify = mamba_server.verify


def event_verify(f):
    """decorator"""
    @wraps(f)
    def wrapper(self, *args):
        current = args[-1]
        if self.event_emitter_con == current.con:
            f(self, *args)
        else:
            raise UnauthorizedError()

    return wrapper


class TerminalHostI(TerminalHost):
    def __init__(self, event_hdl: 'TerminalEventHandlerI'):
        self._terminal = None
        self.clients = []
        self.conn_to_client = {}
        self.logger = mamba_server.logger
        self.event_hdl = event_hdl

        self.event_token = None
        self.event_emitter_con = None

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
            from secrets import token_hex
            event_token = token_hex(8)
            access_endpoint = general_utils.get_access_endpoint()

            self._terminal = IPythonTerminalIO(80, 24,
                                               access_endpoint,
                                               event_token,
                                               self.logger)

            self.event_hdl.set_token(event_token)

            self._terminal.stdout_callback = self._stdout_callback
            self._terminal.terminated_callback = self._terminated_callback
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
        self.terminal.resize(rows, cols)

    def _stdout_callback(self, s: str):
        for client in self.clients:
            try:
                client.stdout(s)
            except Ice.ConnectionLostException:
                pass

    def _connection_closed_callback(self, conn):
        self.clients.remove(self.conn_to_client[conn])

    def _terminated_callback(self):
        self.event_hdl.event_emitter_con = None
        self.event_hdl.event_token = None
        self.terminal = None
        # self.terminal.spawn()


class TerminalEventHandlerI(TerminalEventHandler):
    def __init__(self):
        self.event_token = None
        self.event_emitter_con = None
        self.logger = mamba_server.logger
        self.idle = threading.Event()
        self.idle.set()

    def set_token(self, token):
        self.event_token = token

    # ----------------------
    #   Exposed to emitter
    # ----------------------

    def attach(self, token, current):
        if not self.event_emitter_con and token == self.event_token:
            self.event_token = None
            mamba_server.terminal_con = self.event_emitter_con = current.con
            self.logger.info("Terminal event emitter attached.")
        else:
            self.logger.info("Invalid terminal event emitter attach request.")
            raise Dashboard.UnauthorizedError()

    @event_verify
    def enterExecution(self, cmd, current):
        self.logger.info(f"executed {cmd}")
        self.idle.clear()

    @event_verify
    def leaveExecution(self, result, current):
        self.logger.info(f"result {result}")
        self.idle.set()


def initialize(communicator, adapter):
    event_hdl = TerminalEventHandlerI()
    mamba_server.terminal = TerminalHostI(event_hdl)

    adapter.add(mamba_server.terminal,
                communicator.stringToIdentity("TerminalHost"))
    adapter.add(event_hdl,
                communicator.stringToIdentity("TerminalEventHandler"))

    mamba_server.logger.info("TerminalHost, TerminalEventHandler initialized.")

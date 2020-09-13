from functools import wraps
import threading

import Ice
import MambaICE.Dashboard as Dashboard

import mamba_server
import utils

from mamba_server.experiment_subproc.ipython_terminal_io import IPythonTerminalIO

client_verify = mamba_server.verify


def event_verify(f):
    """decorator"""
    @wraps(f)
    def wrapper(self, *args):
        current = args[-1]
        if self.event_emitter_con == current.con:
            f(self, *args)
        else:
            raise Dashboard.UnauthorizedError()

    return wrapper


class TerminalHostI(Dashboard.TerminalHost):
    def __init__(self, event_hdl):
        self.terminal = None
        self.clients = []
        self.logger = mamba_server.logger
        self.event_hdl = event_hdl

        self.event_token = None
        self.event_emitter_con = None

    @client_verify
    def registerClient(self, client: Dashboard.TerminalClient, current):
        self.logger.info("Terminal mamba_client connected: "
                         + Ice.identityToString(client.ice_getIdentity()))
        client = client.ice_fixed(current.con)
        self.clients.append(client)
        current.con.setCloseCallback(
            lambda conn: self._connection_closed_callback(client))
        self.spawn()

    def spawn(self):
        if not self.terminal:
            from secrets import token_hex
            event_token = token_hex(8)
            access_endpoint = utils.get_access_endpoint()

            self.terminal = IPythonTerminalIO(80, 24,
                                              access_endpoint,
                                              event_token,
                                              self.logger)

            self.event_hdl.set_token(event_token)

            self.terminal.stdout_callback = self._stdout_callback
            self.terminal.terminated_callback = self._terminated_callback
            self.terminal.spawn()
            self.logger.info("Terminal thread spawned, waiting for event "
                             "emitters to attach.")

    @client_verify
    def emitCommand(self, cmd, current):
        self.terminal.stdin(current.encode('utf-8'))

    @client_verify
    def stdin(self, s: bytes, current):
        self.terminal.write(s)

    @client_verify
    def resize(self, rows, cols, current):
        self.terminal.resize(rows, cols)

    def _stdout_callback(self, s: str):
        for client in self.clients:
            try:
                client.stdout(s)
            except Ice.CloseConnectionException:
                self._connection_closed_callback(client)

    def _connection_closed_callback(self, client):
        self.logger.info("Lost connection with client: " +
                         Ice.identityToString(client.ice_getIdentity())
                         )
        self.clients.remove(client)

    def _terminated_callback(self):
        self.event_hdl.event_emitter_con = None
        self.event_hdl.event_token = None
        self.terminal = None
        # self.terminal.spawn()


class TerminalEventHandlerI(Dashboard.TerminalEventHandler):
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

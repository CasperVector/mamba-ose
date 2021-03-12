import zmq
import Ice
from MambaICE.Dashboard import (TerminalHost, TerminalEventHandler)
import mamba_server
from utils import general_utils

class TerminalHostI(TerminalHost):
    def __init__(self, port, event_hdl):
        self.sock = zmq.Context().socket(zmq.REQ)
        self.sock.connect("tcp://127.0.0.1:%d" % port)
        self.event_hdl = event_hdl

    def emitCommand(self, cmd, current=None):
        self.sock.send(cmd.encode("UTF-8") + b"\n")

    def get_slave_endpoint(self):
        return general_utils.format_endpoint("127.0.0.1",
                                             self.event_hdl.slave_port,
                                             "tcp")

class TerminalEventHandlerI(TerminalEventHandler):
    def __init__(self):
        self.slave_port = 0

    def attach(self, port, current):
        self.slave_port = port


def initialize(public_adapter, internal_adapter):
    event_hdl = TerminalEventHandlerI()
    mamba_server.terminal = TerminalHostI(5678, event_hdl)
    public_adapter.add(mamba_server.terminal,
                       Ice.stringToIdentity("TerminalHost"))
    internal_adapter.add(event_hdl,
                         Ice.stringToIdentity("TerminalEventHandler"))
    mamba_server.logger.info("TerminalHost, TerminalEventHandler initialized.")

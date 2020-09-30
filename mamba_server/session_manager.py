from functools import wraps
import Ice

import MambaICE.Dashboard as Dashboard
import mamba_server

ses_mgr = None


def verify(f):
    """decorator"""
    @wraps(f)
    def wrapper(*args):
        assert isinstance(ses_mgr, SessionManagerI)
        current = args[-1]
        if current and isinstance(current, Ice.Current):
            ses_mgr.verify(current)
        return f(*args)

    return wrapper


def set_connection_closed_callback(conn, cbk):
    assert isinstance(ses_mgr, SessionManagerI)
    ses_mgr.add_connection_closed_callback(conn, cbk)


class SessionManagerI(Dashboard.SessionManager):
    def __init__(self):
        self.authorized_conns = {}
        self.logger = mamba_server.logger
        self.conn_closed_callback = {}

    def login(self, username, password, current):
        # pretend to do some verification...

        self.logger.info(f"Client logged in: {username}")
        self.authorized_conns[current.con] = username
        self.conn_closed_callback[current.con] = []
        current.con.setCloseCallback(
            lambda conn: self._connection_closed_callback(conn))

    def logout(self, current):
        # TODO: invoke disconnected callback inside all 'host' object
        # TODO: heart beat check
        if current.con in self.authorized_conns:
            username = self.authorized_conns[current.con]
            self.logger.info(f"Client logged out: {username}")
            self._connection_closed_callback(current.con)
            del self.authorized_conns[current.con]

    def verify(self, current):
        if current.con not in self.authorized_conns:
            raise Dashboard.UnauthorizedError()

    def _connection_closed_callback(self, conn):
        if conn in self.authorized_conns:
            self.logger.info("Lost connection with mamba_client: " +
                             self.authorized_conns[conn])
            for cbk in self.conn_closed_callback[conn]:
                cbk(conn)
            del self.conn_closed_callback[conn]

    def add_connection_closed_callback(self, conn, cbk):
        self.conn_closed_callback[conn].append(cbk)


def initialize(communicator, adapter):
    global ses_mgr
    ses_mgr = mamba_server.session = SessionManagerI()

    adapter.add(mamba_server.session,
                communicator.stringToIdentity("SessionManager"))

    mamba_server.logger.info("SessionManager initialized.")

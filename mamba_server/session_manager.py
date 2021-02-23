import MambaICE.Dashboard as Dashboard
import mamba_server

ses_mgr = None


def set_connection_closed_callback(conn, cbk):
    assert isinstance(ses_mgr, SessionManagerI)
    ses_mgr.add_connection_closed_callback(conn, cbk)

class SessionManagerI(Dashboard.SessionManager):
    def __init__(self):
        self.logger = mamba_server.logger
        self.conn_closed_callback = {}

    def login(self, current):
        self.logger.info(f"Client logged in")
        self.conn_closed_callback[current.con] = []
        current.con.setCloseCallback(
            lambda conn: self._connection_closed_callback(conn))

    def logout(self, current):
        # TODO: invoke disconnected callback inside all 'host' object
        # TODO: heart beat check
        self.logger.info(f"Client logged out")
        self._connection_closed_callback(current.con)

    def _connection_closed_callback(self, conn):
        self.logger.info("Lost connection with mamba_client")
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

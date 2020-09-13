from functools import wraps

import Dashboard
import mamba_server


def verify(f):
    """decorator"""
    @wraps(f)
    def wrapper(*args):
        current = args[-1]
        mamba_server.session.verify(current)
        f(*args)

    return wrapper


class SessionManagerI(Dashboard.SessionManager):
    def __init__(self):
        self.authorized_conns = {}
        self.logger = mamba_server.logger

    def login(self, username, password, current):
        # pretend to do some verification...

        self.logger.info(f"Client logged in: {username}")
        self.authorized_conns[current.con] = username

    def logout(self, current):
        # TODO: invoke disconnected callback inside all 'host' object
        # TODO: heart beat check
        if current.con in self.authorized_conns:
            username = self.authorized_conns[current.con]
            self.logger.info(f"Client logged out: {username}")
            del self.authorized_conns[current.con]

    def verify(self, current):
        if current.con not in self.authorized_conns:
            raise Dashboard.UnauthorizedError()


def initialize(communicator, adapter):
    mamba_server.session = SessionManagerI()

    adapter.add(mamba_server.session,
                communicator.stringToIdentity("SessionManager"))

    mamba_server.logger.info("SessionManager initialized.")

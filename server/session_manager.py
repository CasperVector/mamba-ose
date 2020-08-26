import Dashboard

import server


class SessionManagerI(Dashboard.SessionManager):
    def __init__(self, logger):
        self.authorized_conns = {}
        self.logger = logger

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
    server.session = SessionManagerI(server.logger)

    adapter.add(server.session,
                communicator.stringToIdentity("SessionManager"))

    server.logger.info("SessionManager initialized.")

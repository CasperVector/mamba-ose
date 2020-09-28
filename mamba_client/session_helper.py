import Ice
import time
import threading

import mamba_client
from mamba_client import SessionManagerPrx, UnauthorizedError
from mamba_client.main_window import MainWindow


class SessionHelper:
    def __init__(self, communicator, session_mgr_endpoint, credentials,
                 main_window: MainWindow):
        self.logger = mamba_client.logger
        self.communicator = communicator
        self.endpoint = session_mgr_endpoint
        self.main_window = main_window
        self.username, self.password = credentials
        self.session = None
        self.reconnect_lock = threading.Lock()

    def connect_login(self):
        proxy = self.communicator.stringToProxy(
            f"SessionManager:{self.endpoint}").ice_connectionId("MambaClient")
        self.session = SessionManagerPrx.checkedCast(proxy)
        try:
            self.session.login(self.username, self.password)
        except UnauthorizedError:
            self.main_window.show_masked_popup(
                "Unauthorized user or invalid password.", False)
            return False

        self.session.ice_getConnection().setCloseCallback(
            lambda con: self.on_connection_closed(con))

        return True

    def on_connection_closed(self, con):
        self.logger.error("Lost connection to the server. Trying to reconnect.")
        threading.Thread(name="Reconnect", target=self.popup_try_reconnect,
                         daemon=True).start()
        self.popup_try_reconnect()

    def popup_try_reconnect(self):
        if self.reconnect_lock.locked():
            return

        self.reconnect_lock.acquire()
        self.main_window.show_masked_popup(
            "Lost connection with server, \n"
            "Attempting to re-establish connection...",
            False
        )
        while True:
            try:
                self.logger.info("Reconnect attempt...")
                self.connect_login()
                self.main_window.close_masked_popup()
                break
            except Ice.ConnectionRefusedException:
                time.sleep(3)

    def logout(self):
        try:
            self.session.logout()
            self.session.ice_getConnection().setCloseCallback(None)
            self.session.ice_getConnection().close(
                Ice.ConnectionClose.Gracefully)
        except Ice.ConnectionRefusedException:
            pass


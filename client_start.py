import sys
import logging

import Ice
import Dashboard

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QCoreApplication

import client
import utils
from client.main_window import MainWindow
from client.widgets.terminal import TerminalWidget


if __name__ == "__main__":
    client.logger = logger = logging.getLogger()

    client.config = utils.load_config("client_config.yaml")
    utils.setup_logger(logger)
    ice_endpoint = utils.get_host_endpoint()

    ice_props = Ice.createProperties()
    ice_props.setProperty("Ice.ACM.Close", "0")  # CloseOff
    ice_props.setProperty("Ice.ACM.Heartbeat", "3")  # HeartbeatAlways
    ice_props.setProperty("Ice.ACM.Timeout", "30")

    ice_init_data = Ice.InitializationData()
    ice_init_data.properties = ice_props

    with Ice.initialize(ice_init_data) as communicator:
        QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        app = QApplication([])

        session = Dashboard.SessionManagerPrx.checkedCast(
            communicator.stringToProxy(f"SessionManager:{ice_endpoint}"))
        print(f"SessionManager:{ice_endpoint}")
        # TODO: login window
        session.login("user", "pw")

        try:
            mw = MainWindow()

            mw.add_widget("Terminal",
                          TerminalWidget.get_init_func(communicator,
                                                       ice_endpoint,
                                                       client.logger)
                          )
            mw.set_layout({
                "top": "Terminal"
            })

            mw.show()

            app.exec_()

        finally:
            session.logout()

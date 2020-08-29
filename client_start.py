import sys
import logging

import Ice
from Dashboard import SessionManagerPrx

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QCoreApplication

import client
import utils
import client
from client.main_window import MainWindow
from client.widgets.terminal import TerminalWidget
from client.widgets.plot import PlotWidget
from client.data_client import DataClientI

# --- Ice properties setup ---

ice_props = Ice.createProperties()

# ACM setup for bidirectional connections.

# Don't actively close connection
ice_props.setProperty("Ice.ACM.Close", "0")  # CloseOff
# Always send heartbeat message to keep the connection alive.
ice_props.setProperty("Ice.ACM.Heartbeat", "3")  # HeartbeatAlways
ice_props.setProperty("Ice.ACM.Timeout", "30")

ice_init_data = Ice.InitializationData()
ice_init_data.properties = ice_props

if __name__ == "__main__":
    client.logger = logger = logging.getLogger()

    client.config = utils.load_config("client_config.yaml")
    utils.setup_logger(logger)
    ice_endpoint = utils.get_host_endpoint()

    with Ice.initialize(ice_init_data) as communicator:
        QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        app = QApplication([])

        client.session = SessionManagerPrx.checkedCast(
            communicator.stringToProxy(f"SessionManager:{ice_endpoint}"))

        # TODO: login window
        client.session.login("user", "pw")

        client.data_client = DataClientI(communicator, ice_endpoint, logger)

        try:
            mw = MainWindow()

            mw.add_widget("Terminal",
                          TerminalWidget.get_init_func(communicator,
                                                       ice_endpoint,
                                                       client.logger)
                          )
            mw.add_widget("Plot1",
                          PlotWidget.get_init_func(client.data_client,
                                                   client.logger)
                          )
            mw.set_layout({
                "top": "Terminal",
                "right": "Plot1"
            })

            mw.show()

            app.exec_()

        finally:
            client.session.logout()

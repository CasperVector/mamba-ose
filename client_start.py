import sys
import logging

import Ice
from MambaICE.Dashboard import SessionManagerPrx, DeviceManagerPrx

from PyQt5.QtWidgets import QApplication, QAction
from PyQt5.QtCore import Qt, QCoreApplication

import utils
import mamba_client
from mamba_client.main_window import MainWindow
from mamba_client.widgets.terminal import TerminalWidget
from mamba_client.widgets.plot import PlotWidget
from mamba_client.data_client import DataClientI
from mamba_client.dialogs.device_config import DeviceConfigDialog

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
    mamba_client.logger = logger = logging.getLogger()

    mamba_client.config = utils.load_config("client_config.yaml")
    utils.setup_logger(logger)
    ice_endpoint = utils.get_host_endpoint()

    with Ice.initialize(ice_init_data) as communicator:
        QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        app = QApplication([])

        # We have adapted a connection-based authentication method,
        # which means all communication has be done with a single connection.
        # It requires:
        #  1. The established connection must not be closed all the time.
        #  2. All proxy has to be created with the very connection that the
        #     session.login happens (which is identified by name "MambaClient").
        mamba_client.session = SessionManagerPrx.checkedCast(
            communicator.stringToProxy(f"SessionManager:{ice_endpoint}")
                        .ice_connectionId("MambaClient"))

        # TODO: login window
        mamba_client.credentials = ("user", "password")
        mamba_client.session.login(mamba_client.credentials[0], mamba_client.credentials[1])

        mamba_client.data_client = DataClientI(communicator, ice_endpoint, logger)

        mamba_client.device_manager = DeviceManagerPrx.checkedCast(
            communicator.stringToProxy(f"DeviceManager:{ice_endpoint}")
                .ice_connectionId("MambaClient"))

        try:
            mw = MainWindow()

            mw.add_menu_item("Device",
                             DeviceConfigDialog.get_action(
                                 mamba_client.device_manager,
                                 mw)
                             )
            mw.add_widget("Terminal",
                          TerminalWidget.get_init_func(communicator,
                                                       ice_endpoint,
                                                       mamba_client.logger)
                          )
            mw.add_widget("Plot1",
                          PlotWidget.get_init_func(mamba_client.data_client,
                                                   mamba_client.logger)
                          )
            mw.add_widget("Plot2",
                          PlotWidget.get_init_func(mamba_client.data_client,
                                                   mamba_client.logger)
                          )
            mw.set_layout({
                ("left", "Terminal"),
                ("right", "Plot1"),
                ("right", "Plot2")
            })

            mw.show()

            app.exec_()

        finally:
            mamba_client.session.logout()

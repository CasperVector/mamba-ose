import logging

import Ice
from mamba_client import (SessionManagerPrx, DeviceManagerPrx, TerminalHostPrx,
                          ScanManagerPrx)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QCoreApplication

from utils import general_utils
import mamba_client
from mamba_client.main_window import MainWindow
from mamba_client.widgets.terminal import TerminalWidget
from mamba_client.widgets.plot import PlotWidget
from mamba_client.data_client import DataClientI
from mamba_client.dialogs.device_list_config import DeviceListConfigDialog
from mamba_client.widgets.scan_mechanism import ScanMechanismWidget

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

    mamba_client.config = general_utils.load_config("client_config.yaml")
    general_utils.setup_logger(logger)
    ice_endpoint = general_utils.get_host_endpoint()

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
        mamba_client.terminal_host = TerminalHostPrx.checkedCast(
            communicator.stringToProxy(f"TerminalHost:{ice_endpoint}")
                        .ice_connectionId("MambaClient")
        )
        mamba_client.scan_manager = ScanManagerPrx.checkedCast(
            communicator.stringToProxy(f"ScanManager:{ice_endpoint}")
                .ice_connectionId("MambaClient")
        )

        try:
            mw = MainWindow()

            mw.add_menu_item("Device",
                             DeviceListConfigDialog.get_action(
                                 mamba_client.device_manager,
                                 mw)
                             )
            mw.add_widget("Terminal",
                          TerminalWidget.get_init_func(
                              communicator,
                              mamba_client.terminal_host,
                              mamba_client.logger)
                          )
            mw.add_widget("Plot1",
                          PlotWidget.get_init_func(mamba_client.data_client)
                          )
            mw.add_widget("Plot2",
                          PlotWidget.get_init_func(mamba_client.data_client)
                          )
            mw.add_widget("Scan Mechanism",
                          ScanMechanismWidget.get_init_func(
                              mamba_client.device_manager,
                              mamba_client.terminal_host,
                              mamba_client.scan_manager)
                          )
            mw.set_layout({
                ("left", "Scan Mechanism"),
                ("left", "Terminal"),
                ("right", "Plot1"),
                ("right", "Plot2")
            })

            mw.show()

            app.exec_()

        finally:
            mamba_client.session.logout()

import os
import logging
import argparse

import Ice
from mamba_client import (SessionManagerPrx, DeviceManagerPrx, TerminalHostPrx,
                          ScanManagerPrx)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QCoreApplication

from utils import general_utils
import mamba_client
import mamba_client.session_helper
from mamba_client.main_window import MainWindow
from mamba_client.widgets.terminal import TerminalWidget
from mamba_client.widgets.plot import PlotWidget
from mamba_client.widgets.plot_2d import Plot2DWidget
from mamba_client.data_client import DataClientI
from mamba_client.dialogs.device_list_config import DeviceListConfigDialog
from mamba_client.widgets.scan_mechanism import ScanMechanismWidget
from mamba_client.widgets.motor import MotorWidget


def main():
    parser = argparse.ArgumentParser(
        description="The GUI client of Mamba application."
    )
    parser.add_argument("-c", "--config", dest="config", type=str,
                        default=None, help="the path to the config file")

    args = parser.parse_args()

    # --- Ice properties setup ---
    ice_props = Ice.createProperties()

    # ACM setup for bidirectional connections.

    # Don't actively close connection
    ice_props.setProperty("Ice.ACM.Close", "4")  # CloseOnIdleForceful
    # Always send heartbeat message to keep the connection alive.
    ice_props.setProperty("Ice.ACM.Heartbeat", "3")  # HeartbeatAlways
    ice_props.setProperty("Ice.ACM.Timeout", "10")

    ice_init_data = Ice.InitializationData()
    ice_init_data.properties = ice_props
    mamba_client.logger = logger = logging.getLogger()
    general_utils.setup_logger(logger)

    if args.config:
        assert os.path.exists(args.config), "Invalid config path!"
        logger.info(f"Loading config file {args.config}")
        mamba_client.config = general_utils.load_config(args.config)
    elif os.path.exists("client_config.yaml"):
        logger.info(f"Loading config file ./client_config.yaml")
        mamba_client.config = general_utils.load_config("client_config.yaml")
    else:
        logger.warning("No config file discovered. Using the default one.")
        mamba_client.config = general_utils.load_config(
            general_utils.solve_filepath("client_config.yaml",
                                         os.path.realpath(__file__))
        )

    ice_endpoint = general_utils.get_host_endpoint()

    with Ice.initialize(ice_init_data) as communicator:
        QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        app = QApplication([])
        mw = MainWindow()

        # We have adapted a connection-based authentication method,
        # which means all communication has be done with a single connection.
        # It requires:
        #  1. The established connection must not be closed all the time.
        #  2. All proxy has to be created with the very connection that the
        #     session.login happens (which is identified by name "MambaClient").

        # TODO: login window
        mamba_client.credentials = (
            mamba_client.config['user']['username'],
            mamba_client.config['user']['password']
        )
        mamba_client.session = mamba_client.session_helper.initialize(
            communicator, ice_endpoint, mw, mamba_client.credentials)

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
            mw.add_widget("Plot1D",
                          PlotWidget.get_init_func(mamba_client.data_client)
                          )
            mw.add_widget("Plot2D",
                          Plot2DWidget.get_init_func(mamba_client.data_client)
                          )
            mw.add_widget("Scan Mechanism",
                          ScanMechanismWidget.get_init_func(
                              mamba_client.device_manager,
                              mamba_client.scan_manager,
                              mamba_client.data_client)
                          )
            mw.add_widget("Motor",
                          MotorWidget.get_init_func(mamba_client.device_manager)
                          )
            mw.set_layout({
                ("left", "Motor"),
                ("left", "Scan Mechanism"),
                ("left", "Terminal"),
                ("right", "Plot1D"),
                ("right", "Plot2D")
            })

            mw.show()

            app.exec_()

        finally:
            mamba_client.session.logout()
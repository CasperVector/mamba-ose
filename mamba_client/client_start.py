#!/usr/bin/python3

import os
import logging
import argparse
import zmq

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QCoreApplication
from mamba_server.mzserver import MrClient, MnClient

from utils import general_utils
import mamba_client
from mamba_client.main_window import MainWindow
from mamba_client.widgets.plot import PlotWidget
from mamba_client.widgets.plot_2d import Plot2DWidget
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

    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication([])
    mw = MainWindow()
    ctx = zmq.Context()
    mrc = MrClient(5678, ctx = ctx)
    mnc = MnClient(5678, ctx = ctx)

    mw.add_menu_item("Device", DeviceListConfigDialog.get_action(mrc, mw))
    mw.add_widget("Motor", lambda: MotorWidget(mrc))
    mw.add_widget("Scan Mechanism", lambda: ScanMechanismWidget(mrc, mnc))
    mw.add_widget("Plot1D", lambda: PlotWidget(mnc))
    mw.add_widget("Plot2D", lambda: Plot2DWidget(mnc))
    mw.set_layout({
        ("left", "Motor"),
        ("left", "Scan Mechanism"),
        ("right", "Plot1D"),
        ("right", "Plot2D")
    })

    mnc.start()
    mw.show()
    app.exec_()

if __name__ == "__main__":
    main()


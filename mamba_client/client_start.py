#!/usr/bin/python3

import os
import sys
import yaml
import zmq

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QCoreApplication
from mamba_server.mzserver import MrClient, MnClient

from .widgets.ui import rc_icons
from .main_window import MainWindow
from .widgets.plot import PlotWidget
from .widgets.plot_2d import Plot2DWidget
from .dialogs.device_list_config import DeviceListConfigDialog
from .widgets.scan_mechanism import ScanMechanismWidget
from .widgets.motor import MotorWidget

def main():
    config = sys.argv[1] if len(sys.argv) > 1 \
        else os.path.expanduser("~/.mamba/config.yaml")
    with open(config, "r") as f:
        config = yaml.safe_load(f)

    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication([])
    mw = MainWindow()
    ctx = zmq.Context()
    lport = int(config["network"]["lport"])
    mrc = MrClient(lport, ctx = ctx)
    mnc = MnClient(lport, ctx = ctx)

    mw.add_menu_item("Device", DeviceListConfigDialog.get_action(mrc, mw))
    mw.add_widget("Motor", lambda: MotorWidget(mrc))
    mw.add_widget("Scan Mechanism",
        lambda: ScanMechanismWidget(mrc, mnc, config))
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


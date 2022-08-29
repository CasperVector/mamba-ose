#!/usr/bin/python3

from ..backend.mzserver import config_read, client_build
from PyQt5.QtWidgets import QApplication, QAction
from PyQt5.QtCore import Qt, QCoreApplication

from ..icons import rc_icons
from .main_window import MainWindow
from .widgets.plot import PlotWidget
from .widgets.plot_2d import Plot2DWidget
from .widgets.scan_mechanism import ScanMechanismWidget
from .widgets.motor import MotorWidget
from .dialogs.device_list_config import DeviceListConfigDialog
from .dialogs.auth_dialog import LoginDialog, LogoutDialog

def action_button(parent, txt, f):
    button = QAction(txt, parent)
    button.triggered.connect(f)
    return button

def main(arg = ""):
    config = config_read()
    mrc, mnc = client_build(config)
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication([])
    mw = MainWindow()

    mw.add_menu_item("Device", action_button(mw, "Device Config",
        lambda: DeviceListConfigDialog(mrc, mw).show()))
    mw.add_menu_item("Auth", action_button(mw, "Login",
        lambda: LoginDialog(mrc, mw).show()))
    mw.add_menu_item("Auth", action_button(mw, "Logout",
        lambda: LogoutDialog(mrc, mw).show()))

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


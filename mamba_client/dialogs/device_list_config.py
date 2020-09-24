import struct
import time

from PyQt5.QtWidgets import (QAction, QDialog, QGridLayout, QHBoxLayout,
                             QLabel, QPushButton, QListWidget, QListWidgetItem,
                             QTableWidget, QTableWidgetItem, QSizePolicy,
                             QSpacerItem)
from PyQt5.QtCore import QSize, QEventLoop, Qt
from PyQt5.QtGui import QIcon

import mamba_client
from mamba_client import DeviceManagerPrx, DeviceEntry, DeviceType, DataType
from mamba_client.widgets.device_select import DeviceSelectWidget
from mamba_client.widgets.device_config import DeviceConfigWidget


class DeviceListConfigDialog(QDialog):
    def __init__(self, device_manager: DeviceManagerPrx, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Device")
        self.logger = mamba_client.logger
        self.device_manager = device_manager

        self.layout = QGridLayout()

        self.selected_device = None
        self.device_select_widget = DeviceSelectWidget(device_manager)
        self.layout.addWidget(self.device_select_widget, 0, 0)

        self.config_widget = DeviceConfigWidget(device_manager)
        self.config_widget.config_changed.connect(self.config_changed)
        self.layout.addWidget(self.config_widget, 0, 1)

        self.button_layout = QHBoxLayout()
        button_spacer = QSpacerItem(1, 1, QSizePolicy.Expanding,
                                    QSizePolicy.Fixed)
        self.button_layout.addItem(button_spacer)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setIcon(QIcon(":/icons/delete.png"))
        self.cancel_button.setSizePolicy(QSizePolicy(QSizePolicy.Fixed,
                                                     QSizePolicy.Fixed))
        self.cancel_button.setFocusPolicy(Qt.NoFocus)
        self.cancel_button.clicked.connect(self.close)
        self.button_layout.addWidget(self.cancel_button, Qt.AlignRight)

        self.submit_button = QPushButton("Apply")
        self.submit_button.setIcon(QIcon(":/icons/checkmark.png"))
        self.submit_button.setSizePolicy(QSizePolicy(QSizePolicy.Fixed,
                                                     QSizePolicy.Fixed))
        self.submit_button.setFocusPolicy(Qt.NoFocus)
        self.submit_button.clicked.connect(self.submit)
        self.button_layout.addWidget(self.submit_button, Qt.AlignRight)

        self.layout.addLayout(self.button_layout, 1, 1)
        self.submit_button.setEnabled(False)

        self.setLayout(self.layout)

        self.device_select_widget.device_selected.connect(self.device_selected)
        self.config_widget.config_changed.connect(self.config_changed)

    def device_selected(self, device: DeviceEntry):
        self.submit_button.setEnabled(False)
        self.selected_device = device
        self.config_widget.prepare_config_list(device.name)

    def config_changed(self):
        self.submit_button.setEnabled(True)
        self.submit_button.clearFocus()
        self.config_widget.setFocus()

    def submit(self):
        self.config_widget.submit()
        self.close()

    @classmethod
    def get_action(cls, device_manager, parent=None):
        device_config_action = QAction("Device Config", parent)

        def show_dialog():
            dialog = cls(device_manager, parent)
            dialog.show()

        device_config_action.triggered.connect(show_dialog)

        return device_config_action

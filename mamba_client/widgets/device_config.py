import struct
import time

from PyQt5.QtWidgets import (QWidget, QGridLayout, QVBoxLayout,
                             QLabel, QPushButton, QListWidget, QListWidgetItem,
                             QTableWidget, QTableWidgetItem, QSizePolicy,
                             QSpacerItem)
from PyQt5.QtCore import QSize, QEventLoop, Qt, pyqtSignal
from PyQt5.QtGui import QIcon

import mamba_client
from mamba_client import (DeviceManagerPrx, DeviceEntry, DeviceType, DataType)
from utils.data_utils import to_data_frame, data_frame_to_value


class DeviceConfigWidget(QWidget):
    config_changed = pyqtSignal()

    def __init__(self, device_manager: DeviceManagerPrx, device_id=""):
        super().__init__()
        self.logger = mamba_client.logger
        self.device_manager = device_manager

        self.layout = QVBoxLayout()

        self.old_config_list = []
        self.changed_config_rows = []
        self.config_label = QLabel("Configuration Items")
        self.config_widget = QTableWidget()
        self.config_widget.setRowCount(0)
        self.config_widget.setColumnCount(2)
        self.device_config_items = []
        self.layout.addWidget(self.config_label)
        self.layout.addWidget(self.config_widget)

        self.setLayout(self.layout)

        self.config_widget.itemChanged.connect(self.config_changed.emit)

        self.device_id = device_id
        if device_id:
            self.prepare_config_list(device_id)

    def prepare_config_list(self, device):
        self.device_id = device
        self.config_widget.blockSignals(True)
        self.device_config_items = []  # Remove all items
        # self.changed_config_rows = []
        config_list = self.device_manager.getDeviceConfigurations(device)
        self.old_config_list = config_list
        self.config_widget.setRowCount(len(config_list))
        for i, config in enumerate(config_list):
            name_item = QTableWidgetItem(config.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            value_item = QTableWidgetItem(str(data_frame_to_value(config)))
            self.config_widget.setItem(i, 0, name_item)
            self.config_widget.setItem(i, 1, value_item)
            self.device_config_items.append(value_item)

        self.config_widget.blockSignals(False)

    def submit(self):
        self.config_widget.setCurrentCell(0, 0)
        # for row in self.changed_config_rows:
        for row in range(len(self.old_config_list)):
            value_item = self.config_widget.item(row, 1)
            value_str = value_item.text()

            old = self.old_config_list[row]
            if value_str != str(data_frame_to_value(old)):
                self.device_manager.setDeviceConfiguration(
                    self.device_id,
                    to_data_frame(
                        old.name,
                        old.component,
                        old.type,
                        value_str,
                        time.time()
                    )
                )

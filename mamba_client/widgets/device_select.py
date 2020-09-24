import struct
import time

from PyQt5.QtWidgets import (QWidget, QGridLayout, QLabel, QPushButton,
                             QListWidget, QListWidgetItem, QTableWidget,
                             QTableWidgetItem, QSpacerItem, QVBoxLayout,
                             QSizePolicy)
from PyQt5.QtCore import QSize, QEventLoop, Qt, pyqtSignal
from PyQt5.QtGui import QIcon

import MambaICE

import mamba_client
from mamba_client import (DeviceManagerPrx, DeviceEntry, DeviceType)


class DeviceSelectWidget(QWidget):
    device_selected = pyqtSignal(DeviceEntry)

    def __init__(self,
                 device_manager: DeviceManagerPrx,
                 _filter: dict = None):
        super().__init__()
        self.logger = mamba_client.logger
        self.device_manager = device_manager
        self.filter: dict = _filter if _filter else {}

        self.layout = QVBoxLayout()

        self.selected_device = None
        self.device_select_label = QLabel("Select Device")
        self.device_select_widget = QListWidget()
        self.device_select_items = []
        self.layout.addWidget(self.device_select_label)
        self.layout.addWidget(self.device_select_widget)

        self.setLayout(self.layout)

        self.prepare_device_list()
        self.device_select_widget.itemClicked.connect(self._device_selected)

    def prepare_device_list(self):
        device_list = self._apply_filter(self.device_manager.listDevices())
        for i, device in enumerate(device_list):
            item = QListWidgetItem(self._get_device_display_name(device))
            self.device_select_items.append(device)
            self.device_select_widget.insertItem(i, item)

    def _device_selected(self, item):
        row = self.device_select_widget.row(item)
        device = self.device_select_items[row]
        self.selected_device = device
        self.device_selected.emit(device)

    def _apply_filter(self, device_list):
        new_list = []
        for device in device_list:
            add = True
            if 'type' in self.filter:
                add = add and (device.type in self.filter['type'])
            if 'name_has' in self.filter:
                add = add and (self.filter['name_has'] in device.name)
            if 'name_exclude' in self.filter:
                for name in self.filter['name_exclude']:
                    add = add and (name != device.name)

            if add:
                new_list.append(device)

        return new_list

    def _get_device_display_name(self, device: DeviceEntry):
        if 'type' not in self.filter:
            if device.type == DeviceType.Motor:
                return f"[Motor]    {device.name}"
            elif device.type == DeviceType.Detector:
                return f"[Detector] {device.name}"
        else:
            return device.name

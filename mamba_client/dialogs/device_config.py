import struct
import time

from PyQt5.QtWidgets import (QAction, QDialog, QGridLayout, QLabel, QPushButton,
                             QListWidget, QListWidgetItem, QTableWidget,
                             QTableWidgetItem)
from PyQt5.QtCore import QSize, QEventLoop, Qt

import MambaICE

if hasattr(MambaICE.Dashboard, 'DeviceManagerPrx'):
    from MambaICE.Dashboard import DeviceManagerPrx
else:
    from MambaICE.dashboard_ice import DeviceManagerPrx

if hasattr(MambaICE, 'DeviceType') and hasattr(MambaICE, 'DataType') and \
        hasattr(MambaICE, 'TypedDataFrame') and \
        hasattr(MambaICE, 'DataFrame') and \
        hasattr(MambaICE, 'DataDescriptor') and \
        hasattr(MambaICE, 'DeviceEntry'):
    from MambaICE import (DeviceType, DataType, TypedDataFrame, DataDescriptor,
                          DeviceEntry, DataFrame)
else:
    from MambaICE.types_ice import (DeviceType, DataType, TypedDataFrame,
                                    DataDescriptor, DeviceEntry, DataFrame)

import mamba_client


class DeviceConfigDialog(QDialog):
    def __init__(self, device_manager: DeviceManagerPrx, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Device")
        self.logger = mamba_client.logger
        self.device_manager = device_manager

        self.layout = QGridLayout()

        self.selected_device = None
        self.device_select_label = QLabel("Select Device")
        self.device_select_widget = QListWidget()
        self.device_select_items = []
        self.layout.addWidget(self.device_select_label, 0, 0)
        self.layout.addWidget(self.device_select_widget, 1, 0)

        self.old_config_list = []
        self.changed_config_rows = []
        self.config_label = QLabel("Configuration Items")
        self.config_widget = QTableWidget()
        self.config_widget.setRowCount(0)
        self.config_widget.setColumnCount(2)
        self.device_config_items = []
        self.layout.addWidget(self.config_label, 0, 1)
        self.layout.addWidget(self.config_widget, 1, 1)

        self.submit_button = QPushButton("Submit")
        self.layout.addWidget(self.submit_button, 2, 1)
        self.submit_button.clicked.connect(self.submit)
        self.submit_button.setEnabled(False)

        self.setLayout(self.layout)

        self.prepare_device_list()
        self.device_select_widget.itemClicked.connect(self.device_selected)
        self.config_widget.itemChanged.connect(self.config_changed)

    def prepare_device_list(self):
        self.device_config_items = []
        device_list = self.device_manager.listDevices()
        for i, device in enumerate(device_list):
            item = QListWidgetItem(self._get_device_display_name(device))
            self.device_select_items.append(device)
            self.device_select_widget.insertItem(i, item)

    def prepare_config_list(self, device):
        self.config_widget.blockSignals(True)
        self.device_config_items = []  # Remove all items
        # self.changed_config_rows = []
        config_list = self.device_manager.getDeviceConfigurations(device)
        self.old_config_list = config_list
        self.config_widget.setRowCount(len(config_list))
        for i, config in enumerate(config_list):
            name_item = QTableWidgetItem(config.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            value_item = QTableWidgetItem(
                str(self._to_value(config.value, config.type)))
            self.config_widget.setItem(i, 0, name_item)
            self.config_widget.setItem(i, 1, value_item)
            self.device_config_items.append(value_item)

        self.config_widget.blockSignals(False)

    def device_selected(self, item):
        self.submit_button.setEnabled(False)
        row = self.device_select_widget.row(item)
        device = self.device_select_items[row]
        self.selected_device = device
        self.prepare_config_list(device.name)

    def config_changed(self, item):
        # row = self.config_widget.row(item)
        # col = self.config_widget.column(item)
        # if col != 1:
        #     return
        #
        # self.changed_config_rows.append(row)
        self.submit_button.setEnabled(True)

    def submit(self):
        self.config_widget.setCurrentCell(0, 0)
        # for row in self.changed_config_rows:
        for row in range(len(self.old_config_list)):
            value_item = self.config_widget.item(row, 1)
            value_str = value_item.text()

            old = self.old_config_list[row]
            if value_str != str(self._to_value(old.value, old.type)):
                self.device_manager.setDeviceConfiguration(
                    self.selected_device.name,
                    DataFrame(
                        name=old.name,
                        value=self._pack(old.type, value_str),
                        timestamp=time.time()
                    )
                )

        self.close()

    @staticmethod
    def _get_device_display_name(device: DeviceEntry):
        if device.type == DeviceType.Motor:
            return f"[Motor]    {device.name}"
        elif device.type == DeviceType.Detector:
            return f"[Detector] {device.name}"

    @staticmethod
    def _to_value(value, _type):
        assert isinstance(_type, DataType)
        if _type == DataType.Float:
            return struct.unpack("d", value)[0]
        elif _type == DataType.Integer:
            return struct.unpack("i", value)[0]
        elif _type == DataType.String:
            return value.decode("utf-8")

        return None

    @staticmethod
    def _pack(_type, value):
        assert isinstance(_type, DataType)
        if _type == DataType.Float:
            return struct.pack("d", float(value))
        elif _type == DataType.Integer:
            return struct.pack("i", int(value))
        elif _type == DataType.String:
            return value.encode('utf-8')

    @classmethod
    def get_action(cls, device_manager, parent=None):
        device_config_action = QAction("Device Config", parent)

        def show_dialog():
            dialog = cls(device_manager, parent)
            dialog.show()

        device_config_action.triggered.connect(show_dialog)

        return device_config_action

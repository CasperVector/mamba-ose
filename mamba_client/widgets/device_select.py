from PyQt5.QtWidgets import (QWidget, QGridLayout, QLabel, QPushButton,
                             QListWidget, QListWidgetItem, QTableWidget,
                             QTableWidgetItem, QSpacerItem, QVBoxLayout,
                             QSizePolicy)
from PyQt5.QtCore import QSize, QEventLoop, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
import mamba_client

class DeviceSelectWidget(QWidget):
    device_selected = pyqtSignal(str)

    def __init__(self, mrc, typ, name_exclude = []):
        super().__init__()
        self.logger = mamba_client.logger
        self.mrc = mrc
        self.typ = typ
        self.name_exclude = name_exclude

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
        device_list = []
        for typ in self.typ:
            device_list.extend(sorted(self.mrc.do_dev("keys", typ)))
        for i, device in enumerate(device_list):
            if device in self.name_exclude:
                continue
            item = QListWidgetItem(device)
            self.device_select_items.append(device)
            self.device_select_widget.insertItem(i, item)

    def _device_selected(self, item):
        row = self.device_select_widget.row(item)
        device = self.device_select_items[row]
        self.selected_device = device
        self.device_selected.emit(device)


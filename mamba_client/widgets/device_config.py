from PyQt5.QtWidgets import (QWidget, QGridLayout, QVBoxLayout,
                             QLabel, QPushButton, QListWidget, QListWidgetItem,
                             QTableWidget, QTableWidgetItem, QSizePolicy,
                             QSpacerItem)
from PyQt5.QtCore import QSize, QEventLoop, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
import mamba_client

class DeviceConfigWidget(QWidget):
    config_changed = pyqtSignal()

    def __init__(self, mrc, device_id=""):
        super().__init__()
        self.logger = mamba_client.logger
        self.mrc = mrc
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
        config_list = self.mrc.do_dev("read_configuration", device)
        config_list = sorted(config_list.items())
        self.old_config_list = config_list
        self.config_widget.setRowCount(len(config_list))
        for i, (k, v) in enumerate(config_list):
            name_item = QTableWidgetItem(k)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            value_item = QTableWidgetItem(str(v["value"]))
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
            values = [old[1]["value"], value_str]
            if values[1] != str(values[0]):
                for dtyp in float, int:
                    if isinstance(values[0], dtyp):
                        values[1] = dtyp(values[1])
                self.mrc.do_cmd("%s.set(%r).wait()\n" % (old[0], values[1]))


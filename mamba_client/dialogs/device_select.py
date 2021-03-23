from PyQt5.QtWidgets import (QAction, QDialog, QVBoxLayout, QLabel, QPushButton,
                             QListWidget, QListWidgetItem, QTableWidget,
                             QTableWidgetItem, QSpacerItem, QHBoxLayout,
                             QSizePolicy)
from PyQt5.QtCore import QSize, QEventLoop, Qt
from PyQt5.QtGui import QIcon

import mamba_client
from mamba_client import (DeviceManagerPrx, DeviceEntry)
from mamba_client.widgets.device_select import DeviceSelectWidget


class DeviceSelectDialog(QDialog):
    def __init__(self,
                 device_manager: DeviceManagerPrx,
                 _filter=None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Device")
        self.logger = mamba_client.logger
        self.device_manager = device_manager
        self.filter = _filter

        self.layout = QVBoxLayout()

        self.selected_device = None
        self.device_select_widget = DeviceSelectWidget(device_manager, _filter)
        self.layout.addWidget(self.device_select_widget)

        self.button_layout = QHBoxLayout()
        button_spacer = QSpacerItem(1, 1, QSizePolicy.Expanding,
                                    QSizePolicy.Fixed)
        self.button_layout.addItem(button_spacer)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setIcon(QIcon(":/icons/delete.png"))
        self.cancel_button.setSizePolicy(QSizePolicy(QSizePolicy.Fixed,
                                                     QSizePolicy.Fixed))
        self.cancel_button.setFocusPolicy(Qt.NoFocus)
        self.cancel_button.clicked.connect(self.reject)
        self.button_layout.addWidget(self.cancel_button, Qt.AlignRight)

        self.submit_button = QPushButton("Select")
        self.submit_button.setIcon(QIcon(":/icons/checkmark.png"))
        self.submit_button.setSizePolicy(QSizePolicy(QSizePolicy.Fixed,
                                                     QSizePolicy.Fixed))
        self.submit_button.setFocusPolicy(Qt.NoFocus)
        self.submit_button.clicked.connect(self.submit)
        self.button_layout.addWidget(self.submit_button, Qt.AlignRight)

        self.layout.addLayout(self.button_layout)
        self.submit_button.setEnabled(False)

        self.setLayout(self.layout)

        self.device_select_widget.device_selected.connect(self.device_selected)

    def device_selected(self, device: DeviceEntry):
        self.selected_device = device
        self.submit_button.setEnabled(True)

    def submit(self):
        self.accept()

    def display(self) -> DeviceEntry:
        loop = QEventLoop()
        self.finished.connect(loop.quit)
        self.show()
        loop.exec()

        return self.selected_device

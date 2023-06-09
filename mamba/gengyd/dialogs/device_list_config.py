from PyQt5.QtWidgets import (QDialog, QGridLayout, QHBoxLayout,
                             QPushButton, QSizePolicy, QSpacerItem)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

from ..widgets.device_select import DeviceSelectWidget
from ..widgets.device_config import DeviceConfigWidget

class DeviceListConfigDialog(QDialog):
    def __init__(self, mrc, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Device")
        self.mrc = mrc
        self.layout = QGridLayout()

        self.selected_device = None
        self.device_select_widget = DeviceSelectWidget(mrc, "DM")
        self.layout.addWidget(self.device_select_widget, 0, 0)

        self.config_widget = DeviceConfigWidget(mrc)
        self.config_widget.config_changed.connect(self.config_changed)
        self.layout.addWidget(self.config_widget, 0, 1)

        self.button_layout = QHBoxLayout()
        button_spacer = QSpacerItem(1, 1, QSizePolicy.Expanding,
                                    QSizePolicy.Fixed)
        self.button_layout.addItem(button_spacer)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setIcon(QIcon(":/delete.png"))
        self.cancel_button.setSizePolicy(QSizePolicy(QSizePolicy.Fixed,
                                                     QSizePolicy.Fixed))
        self.cancel_button.setFocusPolicy(Qt.NoFocus)
        self.cancel_button.clicked.connect(self.close)
        self.button_layout.addWidget(self.cancel_button, Qt.AlignRight)

        self.submit_button = QPushButton("Apply")
        self.submit_button.setIcon(QIcon(":/checkmark.png"))
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

    def device_selected(self, device):
        self.submit_button.setEnabled(False)
        self.selected_device = device
        self.config_widget.prepare_config_list(device)

    def config_changed(self):
        self.submit_button.setEnabled(True)
        self.submit_button.clearFocus()
        self.config_widget.setFocus()

    def submit(self):
        self.config_widget.submit()
        self.close()


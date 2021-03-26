from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QSizePolicy, QSpacerItem)

from ..widgets.device_config import DeviceConfigWidget


class DeviceConfigDialog(QDialog):
    def __init__(self, device_id, mrc, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Configure Device: {device_id}")
        self.device_id = device_id
        self.mrc = mrc

        self.layout = QVBoxLayout()

        self.old_config_list = []
        self.changed_config_rows = []
        self.config_widget = DeviceConfigWidget(mrc, device_id)
        self.layout.addWidget(self.config_widget)

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

        self.layout.addLayout(self.button_layout)
        self.submit_button.setEnabled(False)

        self.setLayout(self.layout)

        self.config_widget.prepare_config_list(self.device_id)
        self.config_widget.config_changed.connect(self.config_changed)

    def config_changed(self):
        self.submit_button.setEnabled(True)
        self.submit_button.clearFocus()
        self.config_widget.setFocus()

    def submit(self):
        self.config_widget.submit()
        self.close()

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QIcon, QPixmap, QPalette
from PyQt5.QtCore import Qt, pyqtSignal, QTimer

import mamba_client
from mamba_client import (DeviceManagerPrx, DeviceEntry, DeviceType)
from mamba_client.dialogs.device_select import DeviceSelectDialog
from utils.data_utils import DataType, data_frame_to_value, to_data_frame
from .ui.ui_motorwidget import Ui_MotorWidget


class MotorWidget(QWidget):
    update = pyqtSignal()

    def __init__(self, device_manager: DeviceManagerPrx, motor_id=""):
        super().__init__()

        self.logger = mamba_client.logger
        self.motor_id = motor_id
        self.device_manager = device_manager
        self.cur_pos = 0
        self.editing_abs = False
        self.timer = QTimer()
        self.timer.timeout.connect(self._update)
        self.timer.start(500)
        self.update.connect(self._update)

        self.ui = Ui_MotorWidget()
        self.ui.setupUi(self)
        self.ui.moveBtn.setIcon(QIcon(QPixmap(":/icons/playback-play.png")))
        self.ui.moveBtn.setEnabled(False)
        self.ui.moveBtn.clicked.connect(self.move_btn_clicked)
        self.ui.motorSelectBtn.clicked.connect(self.select_motor_clicked)
        self.ui.targetAbsEdit.textChanged.connect(self.sync_abs_rel_edit)
        self.ui.targetRelEdit.textChanged.connect(self.sync_abs_rel_edit)
        self.ui.targetAbsEdit.setEnabled(False)
        self.ui.targetRelEdit.setEnabled(False)

        def relFocusIn(evt):
            nonlocal self
            self.editing_abs = False

        def absFocusIn(evt):
            nonlocal self
            self.editing_abs = True

        self.ui.targetRelEdit.focusInEvent = relFocusIn
        self.ui.targetAbsEdit.focusInEvent = absFocusIn

    def select_motor_clicked(self):
        dialog = DeviceSelectDialog(
            self.device_manager,
            {
                'type': [DeviceType.Motor]
            },
            self)
        device = dialog.display()
        if device:
            self.motor_id = device.name
            self.ui.targetAbsEdit.setEnabled(True)
            self.ui.targetRelEdit.setEnabled(True)
            self.update.emit()

    def move_btn_clicked(self):
        self._update()
        self.device_manager.setDeviceValue(
            self.motor_id,
            to_data_frame(
                "",
                "",
                DataType.Float,
                float(self.ui.targetAbsEdit.text())
            )
        )

    def _update(self):
        if self.motor_id:
            data_frames = self.device_manager.getDeviceReadings(
                self.motor_id)

            print(data_frames)

            df = None
            if len(data_frames) == 0:
                return
            elif len(data_frames) == 1:
                df = data_frames[0]
            else:
                for data_frame in data_frames:
                    if "setpoint" in data_frame.name:
                        continue
                    if data_frame.type != DataType.Float and data_frame.type != DataType.Integer:
                        continue
                    df = data_frame
                    break

            if not df:
                return

            self.cur_pos = data_frame_to_value(df)
            self.ui.motorNameLabel.setText(self.motor_id)
            self.ui.curPosLabel.setText("{:.2f}".format(self.cur_pos))
            self.sync_abs_rel_edit()

    def sync_abs_rel_edit(self):
        if not self.ui.targetAbsEdit.text() and \
                not self.ui.targetRelEdit.text():
            return
        try:
            if self.ui.targetAbsEdit.text():
                abs_val = float(self.ui.targetAbsEdit.text())
                self.set_text_color(self.ui.targetAbsEdit, Qt.black)
                self.ui.moveBtn.setEnabled(True)
            else:
                abs_val = self.cur_pos
        except ValueError:
            self.set_text_color(self.ui.targetAbsEdit, Qt.red)
            self.ui.moveBtn.setEnabled(False)
            return

        try:
            if self.ui.targetRelEdit.text():
                rel_val = float(self.ui.targetRelEdit.text())
                self.set_text_color(self.ui.targetRelEdit, Qt.black)
                self.ui.moveBtn.setEnabled(True)
            else:
                rel_val = 0
        except ValueError:
            self.set_text_color(self.ui.targetRelEdit, Qt.red)
            self.ui.moveBtn.setEnabled(False)
            return

        if self.editing_abs:
            self.ui.targetRelEdit.blockSignals(True)
            self.ui.targetRelEdit.setText("{:.2f}".format(
                abs_val - self.cur_pos))
            self.ui.targetRelEdit.blockSignals(False)
        else:
            self.ui.targetAbsEdit.blockSignals(True)
            self.ui.targetAbsEdit.setText("{:.2f}".format(
                rel_val + self.cur_pos))
            self.ui.targetAbsEdit.blockSignals(False)

    @staticmethod
    def set_text_color(text_edit, color):
        pal = text_edit.palette()
        pal.setColor(QPalette.Text, color)
        text_edit.setPalette(pal)

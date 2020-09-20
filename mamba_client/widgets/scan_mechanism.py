from typing import List
from collections import namedtuple

from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QMessageBox
from PyQt5.QtGui import QIcon, QColor, QPixmap, QBrush

from PyQt5.QtCore import Qt, QSize

import mamba_client
from mamba_client import DeviceManagerPrx, DeviceType, TerminalHostPrx
from mamba_client.dialogs.device_setect import DeviceSelectDialog
from mamba_client.dialogs.device_config import DeviceConfigDialog
from .ui.ui_scanmechanismwidget import Ui_ScanMechanicsWidget

MOTOR_ADD_COL = 0
MOTOR_NAME_COL = 1
MOTOR_SETUP_COL = 2
MOTOR_START_COL = 3
MOTOR_END_COL = 4
MOTOR_NUM_COL = 5

DETECTOR_ADD_COL = 0
DETECTOR_NAME_COL = 1
DETECTOR_SETUP_COL = 2

MotorScanInstruction = namedtuple('MotorScanInstruction', [
    'name', 'start', 'end', 'point_num'
])


class ScanInstructionSet:
    def __init__(self, motors: List[MotorScanInstruction], detectors: list):
        self.motors = motors
        self.detectors = detectors

    def generate_command(self):
        commands = []
        dets = [f'dets.{name}' for name in self.detectors]
        det_str = str(dets).replace("'", "")
        command = ""
        if len(self.motors) > 1:
            commands.append("from bluesky.plans import grid_scan")
            command += f"RE(grid_scan({det_str},\n"
        else:
            commands.append("from bluesky.plans import scan")
            command += f"RE(scan({det_str},\n"

        for motor in self.motors:
            command += f"motors.{motor.name}, {float(motor.start)}, " \
                       f"{float(motor.end)}, {int(motor.point_num)},\n"

        command = command[:-2]
        command += "))"

        commands.append(command)

        return commands


class ScanMechanismWidget(QWidget):
    def __init__(self, device_manager: DeviceManagerPrx,
                 terminal: TerminalHostPrx):
        super().__init__()
        self.logger = mamba_client.logger
        self.device_manager = device_manager
        self.terminal_host = terminal

        self.scanned_motors = {}
        self.scanned_detectors = []

        self.ui = Ui_ScanMechanicsWidget()
        self.ui.setupUi(self)

        for btn, pix in {
            self.ui.runButton: QPixmap(":/icons/playback-play.png"),
            self.ui.pauseButton: QPixmap(":/icons/playback-pause.png"),
            self.ui.stopButton: QPixmap(":/icons/playback-stop.png")
        }.items():
            icon = QIcon(pix)
            btn.setIcon(icon)
            size = QSize(32, 32)
            btn.setIconSize(size)
            btn.resize(48, 48)

        self.setting_icon = QIcon(":/icons/settings.png")
        self.add_icon = QIcon(":/icons/list-add.png")
        self.remove_icon = QIcon(":/icons/list-remove.png")

        self.ui.motorTableWidget.itemClicked.connect(self.motor_table_clicked)
        self.ui.motorTableWidget.itemChanged.connect(self.motor_table_changed)
        self.ui.detectorTableWidget.itemClicked.connect(self.detector_table_clicked)
        self.ui.runButton.clicked.connect(self.run)

        self.add_motor()
        self.add_detector()

    def motor_table_clicked(self, item):
        row = self.ui.motorTableWidget.row(item)
        col = self.ui.motorTableWidget.column(item)

        if col == MOTOR_ADD_COL:
            if row == self.ui.motorTableWidget.rowCount() - 1:
                dialog = DeviceSelectDialog(
                    self.device_manager,
                    {
                        'type': [DeviceType.Motor],
                        'name_exclude': self.scanned_motors.keys()
                    },
                    self)
                device = dialog.display()
                if device:
                    self.scanned_motors[device.name] = MotorScanInstruction(
                        name=device.name,
                        start=None,
                        end=None,
                        point_num=None
                    )
                    self.add_motor(device.name)
            else:
                name_to_delete = self.ui.motorTableWidget.item(
                    row, MOTOR_NAME_COL).text()
                del self.scanned_motors[name_to_delete]
                self.ui.motorTableWidget.removeRow(row)
        elif col == MOTOR_SETUP_COL:
            if row < self.ui.motorTableWidget.rowCount() - 1:
                name = self.ui.motorTableWidget.item(row,
                                                     MOTOR_NAME_COL).text()
                dialog = DeviceConfigDialog(name, self.device_manager, self)
                dialog.show()

    def detector_table_clicked(self, item):
        row = self.ui.detectorTableWidget.row(item)
        col = self.ui.detectorTableWidget.column(item)

        if col == DETECTOR_ADD_COL:
            if row == self.ui.detectorTableWidget.rowCount() - 1:
                dialog = DeviceSelectDialog(
                    self.device_manager,
                    {
                        'type': [DeviceType.Detector],
                        'name_exclude': self.scanned_detectors
                    },
                    self)
                device = dialog.display()
                if device:
                    self.scanned_detectors.append(device.name)
                    self.add_detector(device.name)
            else:
                name_to_delete = self.ui.detectorTableWidget.item(
                    row, DETECTOR_NAME_COL).text()
                self.scanned_detectors.remove(name_to_delete)
                self.ui.detectorTableWidget.removeRow(row)
        elif col == DETECTOR_SETUP_COL:
            if row < self.ui.detectorTableWidget.rowCount() - 1:
                name = self.ui.detectorTableWidget.item(
                    row, DETECTOR_NAME_COL).text()
                dialog = DeviceConfigDialog(name, self.device_manager, self)
                dialog.show()

    def motor_table_changed(self, item):
        row = self.ui.motorTableWidget.row(item)
        col = self.ui.motorTableWidget.column(item)
        name = self.ui.motorTableWidget.item(row,
                                             MOTOR_NAME_COL).text()

        if col in [MOTOR_START_COL, MOTOR_END_COL, MOTOR_NUM_COL]:
            text = item.text()
            try:
                num = float(text)
                item.setForeground(QBrush())
                inst = self.scanned_motors[name]
                if col == MOTOR_START_COL:
                    self.scanned_motors[name] = MotorScanInstruction(
                        name=name,
                        start=num,
                        end=inst.end,
                        point_num=inst.point_num
                    )
                elif col == MOTOR_END_COL:
                    self.scanned_motors[name] = MotorScanInstruction(
                        name=name,
                        start=inst.start,
                        end=num,
                        point_num=inst.point_num
                    )
                elif col == MOTOR_NUM_COL:
                    self.scanned_motors[name] = MotorScanInstruction(
                        name=name,
                        start=inst.start,
                        end=inst.end,
                        point_num=num
                    )
            except ValueError:
                item.setForeground(Qt.red)

    def add_motor(self, motor_id=""):
        self.ui.motorTableWidget.blockSignals(True)
        row = self.ui.motorTableWidget.rowCount() - 1

        if row == -1:
            self.ui.motorTableWidget.insertRow(0)
            row_height = self.ui.motorTableWidget.rowHeight(0)
            self.ui.motorTableWidget.setColumnWidth(MOTOR_ADD_COL, row_height)
            self.ui.motorTableWidget.setColumnWidth(MOTOR_SETUP_COL, row_height)

            for c in [MOTOR_NAME_COL, MOTOR_START_COL,
                      MOTOR_END_COL, MOTOR_NUM_COL]:
                self.ui.motorTableWidget.setItem(
                    row + 1, c, self._get_table_uneditable_item())
        else:
            if not motor_id:
                return
            motor_item = self._get_table_uneditable_item()
            motor_item.setText(motor_id)
            self.ui.motorTableWidget.setItem(row, MOTOR_NAME_COL, motor_item)

            remove_item = self._get_table_icon_item(self.remove_icon)
            self.ui.motorTableWidget.setItem(row, MOTOR_ADD_COL, remove_item)

            setup_item = self._get_table_icon_item(self.setting_icon)
            self.ui.motorTableWidget.setItem(row, MOTOR_SETUP_COL, setup_item)

            for c in [MOTOR_START_COL, MOTOR_END_COL, MOTOR_NUM_COL]:
                self.ui.motorTableWidget.setItem(
                    row, c, self._get_table_editable_item())

            self.ui.motorTableWidget.insertRow(row + 1)

        add_item = self._get_table_icon_item(self.add_icon)
        self.ui.motorTableWidget.setItem(row + 1, MOTOR_ADD_COL, add_item)
        self.ui.motorTableWidget.blockSignals(False)

    def add_detector(self, detector_id=""):
        self.ui.detectorTableWidget.blockSignals(True)
        row = self.ui.detectorTableWidget.rowCount() - 1

        if row == -1:
            self.ui.detectorTableWidget.insertRow(0)
            row_height = self.ui.detectorTableWidget.rowHeight(0)
            self.ui.detectorTableWidget.setColumnWidth(DETECTOR_ADD_COL, row_height)
            self.ui.detectorTableWidget.setColumnWidth(DETECTOR_SETUP_COL, row_height)

            self.ui.detectorTableWidget.setItem(
                row + 1, DETECTOR_SETUP_COL, self._get_table_uneditable_item())
        else:
            if not detector_id:
                return
            detector_item = self._get_table_uneditable_item()
            detector_item.setText(detector_id)
            self.ui.detectorTableWidget.setItem(row, DETECTOR_NAME_COL, detector_item)

            remove_item = self._get_table_icon_item(self.remove_icon)
            self.ui.detectorTableWidget.setItem(row, DETECTOR_ADD_COL, remove_item)

            setup_item = self._get_table_icon_item(self.setting_icon)
            self.ui.detectorTableWidget.setItem(row, DETECTOR_SETUP_COL, setup_item)

            self.ui.detectorTableWidget.insertRow(row + 1)

        add_item = self._get_table_icon_item(self.add_icon)
        self.ui.detectorTableWidget.setItem(row + 1, DETECTOR_ADD_COL, add_item)
        self.ui.detectorTableWidget.blockSignals(False)

    def run(self):
        if self.scanned_motors and self.scanned_detectors:
            for motor in self.scanned_motors.values():
                if motor.start is None \
                        and motor.end is None \
                        and motor.point_num is None:
                    QMessageBox.warning(
                        self,
                        "Mamba",
                        "Invalid values of scan parameters.\n",
                        QMessageBox.Ok)
                    return False

            inst = ScanInstructionSet(
                list(self.scanned_motors.values()), self.scanned_detectors)
            for cmd in inst.generate_command():
                self.terminal_host.emitCommand(cmd)

    @staticmethod
    def _get_table_icon_item(icon):
        item = QTableWidgetItem()
        item.setIcon(icon)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    @staticmethod
    def _get_table_uneditable_item():
        item = QTableWidgetItem()
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    @staticmethod
    def _get_table_editable_item():
        item = QTableWidgetItem()
        return item

    @classmethod
    def get_init_func(cls, device_manager: DeviceManagerPrx,
                      terminal_host: TerminalHostPrx):
        return lambda: cls(device_manager, terminal_host)



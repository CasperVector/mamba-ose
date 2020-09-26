from typing import List
from collections import namedtuple

from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QMessageBox, QInputDialog
from PyQt5.QtGui import QIcon, QColor, QPixmap, QBrush

from PyQt5.QtCore import Qt, QSize

import MambaICE
import mamba_client
from mamba_client import (DeviceManagerPrx, DeviceType, TerminalHostPrx)
from mamba_client.dialogs.device_setect import DeviceSelectDialog
from mamba_client.dialogs.device_config import DeviceConfigDialog
from .ui.ui_scanmechanismwidget import Ui_ScanMechanicsWidget

if hasattr(MambaICE.Dashboard, 'ScanManagerPrx') and \
        hasattr(MambaICE.Dashboard, 'MotorScanInstruction') and \
        hasattr(MambaICE.Dashboard, 'ScanInstruction') and \
        hasattr(MambaICE.Dashboard, 'UnauthorizedError'):
    from MambaICE.Dashboard import (ScanManagerPrx, MotorScanInstruction,
                                    ScanInstruction, UnauthorizedError)
else:
    from MambaICE.dashboard_ice import (ScanManagerPrx, MotorScanInstruction,
                                        ScanInstruction, UnauthorizedError)

MOTOR_ADD_COL = 0
MOTOR_NAME_COL = 1
MOTOR_SETUP_COL = 2
MOTOR_START_COL = 3
MOTOR_END_COL = 4
MOTOR_NUM_COL = 5

DETECTOR_ADD_COL = 0
DETECTOR_NAME_COL = 1
DETECTOR_SETUP_COL = 2


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
                       f"{float(motor.stop)}, {int(motor.point_num)},\n"

        command = command[:-2]
        command += "))"

        commands.append(command)

        return commands


class ScanMechanismWidget(QWidget):
    def __init__(self, device_manager: DeviceManagerPrx,
                 scan_manager: ScanManagerPrx):
        super().__init__()
        self.logger = mamba_client.logger
        self.device_manager = device_manager
        self.scan_manager = scan_manager

        self.scanned_motors = {}
        self.scanned_detectors = []

        self.ui = Ui_ScanMechanicsWidget()
        self.ui.setupUi(self)

        for btn, (pix, size) in [
            (self.ui.runButton, (QPixmap(":/icons/playback-play.png"), 32)),
            (self.ui.pauseButton, (QPixmap(":/icons/playback-pause.png"), 32)),
            (self.ui.stopButton, (QPixmap(":/icons/playback-stop.png"), 32)),
            (self.ui.addPlanButton, (QPixmap(":/icons/new-document.png"), 0)),
            (self.ui.savePlanButton, (QPixmap(":/icons/save.png"), 32))
        ]:
            icon = QIcon(pix)
            btn.setIcon(icon)
            if size > 0:
                btn.setIconSize(QSize(size, size))

        self.setting_icon = QIcon(":/icons/settings.png")
        self.add_icon = QIcon(":/icons/list-add.png")
        self.remove_icon = QIcon(":/icons/list-remove.png")

        self.ui.motorTableWidget.itemClicked.connect(self.motor_table_clicked)
        self.ui.motorTableWidget.itemChanged.connect(self.motor_table_changed)
        self.ui.detectorTableWidget.itemClicked.connect(self.detector_table_clicked)
        self.ui.runButton.clicked.connect(self.run)
        self.ui.savePlanButton.clicked.connect(self.save_scan_plan)
        self.ui.planComboBox.currentIndexChanged.connect(self.plan_combo_index_changed)
        self.ui.addPlanButton.clicked.connect(self.create_new_plan_clicked)

        self.populate_plan_combo()

        self.editing_new_plan = False
        self.editing_plan = False

    def create_new_plan_clicked(self):
        name, ok = QInputDialog.getText(self, "Create new plan", "Plan name:")
        if ok and name:
            self.ui.planComboBox.blockSignals(True)
            idx = self.ui.planComboBox.count()
            self.ui.planComboBox.insertItem(
                idx,
                name)
            self.ui.planComboBox.setCurrentIndex(idx)
            self.editing_new_plan = True
            self.reset_motor_detector_list()
            self.ui.planComboBox.blockSignals(False)

    def plan_changed(self):
        item = self.ui.planComboBox.model().item(
            self.ui.planComboBox.currentIndex())
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        self.editing_plan = True

    def populate_plan_combo(self):
        plans = self.scan_manager.listScanPlans()
        if plans:
            for plan in plans:
                self.ui.planComboBox.addItem(plan)
                self.plan_combo_index_changed(
                    self.ui.planComboBox.currentIndex())
        else:
            self.add_motor()
            self.add_detector()

    def plan_combo_index_changed(self, index):
        self.ui.planComboBox.setEnabled(False)
        self.populate_plan_inst(self.ui.planComboBox.itemText(index))
        self.ui.planComboBox.setEnabled(True)

    def populate_plan_inst(self, name):
        self.ui.motorTableWidget.setEnabled(False)
        self.ui.detectorTableWidget.setEnabled(False)
        self.reset_motor_detector_list()
        plan = self.scan_manager.getScanPlan(name)
        for motor in plan.motors:
            self.add_motor(motor.name, motor.start, motor.stop, motor.point_num)

        for detector in plan.detectors:
            self.add_detector(detector)
        self.ui.motorTableWidget.setEnabled(True)
        self.ui.detectorTableWidget.setEnabled(True)

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
                        stop=None,
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
        self.plan_changed()
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
                        stop=inst.stop,
                        point_num=inst.point_num
                    )
                elif col == MOTOR_END_COL:
                    self.scanned_motors[name] = MotorScanInstruction(
                        name=name,
                        start=inst.start,
                        stop=num,
                        point_num=inst.point_num
                    )
                elif col == MOTOR_NUM_COL:
                    self.scanned_motors[name] = MotorScanInstruction(
                        name=name,
                        start=inst.start,
                        stop=inst.stop,
                        point_num=num
                    )
            except ValueError:
                item.setForeground(Qt.red)

    def add_motor(self, motor_id="", start=None, stop=None, point_num=None):
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

            for num, col in [
                (start, MOTOR_START_COL),
                (stop, MOTOR_END_COL),
                (point_num, MOTOR_NUM_COL)
            ]:
                num = num if not None else ""
                item = self._get_table_editable_item(num)
                self.ui.motorTableWidget.setItem(row, col, item)

            remove_item = self._get_table_icon_item(self.remove_icon)
            self.ui.motorTableWidget.setItem(row, MOTOR_ADD_COL, remove_item)

            setup_item = self._get_table_icon_item(self.setting_icon)
            self.ui.motorTableWidget.setItem(row, MOTOR_SETUP_COL, setup_item)

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

    def reset_motor_detector_list(self):
        self.ui.motorTableWidget.blockSignals(True)
        for row in range(self.ui.motorTableWidget.rowCount()):
            self.ui.motorTableWidget.removeRow(row)
        self.add_motor()
        self.ui.motorTableWidget.blockSignals(False)

        self.ui.detectorTableWidget.blockSignals(True)
        for row in range(self.ui.detectorTableWidget.rowCount()):
            self.ui.detectorTableWidget.removeRow(row)
        self.add_detector()
        self.ui.detectorTableWidget.blockSignals(False)

    def validate_plan_input(self):
        if self.scanned_motors and self.scanned_detectors:
            for motor in self.scanned_motors.values():
                if motor.start is not None \
                        and motor.stop is not None \
                        and motor.point_num is not None:
                    return True
        return False

    def run(self):
        if self.save_scan_plan():
            name = self.ui.planComboBox.currentText()
            self.scan_manager.runScan(name)

    def save_scan_plan(self):
        if not self.validate_plan_input():
            QMessageBox.warning(
                self,
                "Mamba",
                "Invalid values of scan parameters.\n",
                QMessageBox.Ok)
            return False
        name = self.ui.planComboBox.currentText()
        inst = ScanInstruction(
            motors=list(self.scanned_motors.values()),
            detectors=self.scanned_detectors
        )
        self.scan_manager.setScanPlan(name, inst)
        return True

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
    def _get_table_editable_item(text=None):
        if not text:
            text = ""
        item = QTableWidgetItem()
        item.setText(str(text))
        return item

    @classmethod
    def get_init_func(cls, device_manager: DeviceManagerPrx,
                      scan_manager: ScanManagerPrx):
        return lambda: cls(device_manager, scan_manager)



from datetime import datetime, timedelta
from functools import partial
from typing import List
from collections import namedtuple

from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QMessageBox, QInputDialog
from PyQt5.QtGui import QIcon, QColor, QPixmap, QBrush

from PyQt5.QtCore import Qt, QSize, QTimer, QMutex, pyqtSignal

import MambaICE
import mamba_client
from mamba_client import (DeviceManagerPrx, DeviceType, FileWriterHostPrx)
from mamba_client.data_client import DataClientI
from mamba_client.dialogs.device_setect import DeviceSelectDialog
from mamba_client.dialogs.device_config import DeviceConfigDialog
from mamba_client.dialogs.scan_file_option import ScanFileOptionDialog
from .ui.ui_scanmechanismwidget import Ui_ScanMechanicsWidget

if hasattr(MambaICE.Dashboard, 'ScanManagerPrx') and \
        hasattr(MambaICE.Dashboard, 'MotorScanInstruction') and \
        hasattr(MambaICE.Dashboard, 'ScanDataOption') and \
        hasattr(MambaICE.Dashboard, 'ScanInstruction') and \
        hasattr(MambaICE.Dashboard, 'UnauthorizedError'):
    from MambaICE.Dashboard import (ScanManagerPrx, MotorScanInstruction,
                                    ScanInstruction, ScanDataOption,
                                    UnauthorizedError)
else:
    from MambaICE.dashboard_ice import (ScanManagerPrx, MotorScanInstruction,
                                        ScanInstruction, ScanDataOption,
                                        UnauthorizedError)

from utils.data_utils import DataDescriptor

MOTOR_ADD_COL = 0
MOTOR_NAME_COL = 1
MOTOR_SETUP_COL = 2
MOTOR_START_COL = 3
MOTOR_END_COL = 4
MOTOR_NUM_COL = 5

DETECTOR_ADD_COL = 0
DETECTOR_NAME_COL = 1
DETECTOR_SETUP_COL = 2

PAUSED = 1
RESUMED = 2


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
    update_status_sig = pyqtSignal(str, int, int)

    def __init__(self, device_manager: DeviceManagerPrx,
                 scan_manager: ScanManagerPrx,
                 data_client: DataClientI,
                 file_writer: FileWriterHostPrx):
        super().__init__()
        self.logger = mamba_client.logger
        self.device_manager = device_manager
        self.scan_manager = scan_manager
        self.data_client = data_client
        self.file_writer = file_writer

        self.scanned_motors = {}
        self.scanned_detectors = []
        self.scan_data_options = {}

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
        self.ui.pauseButton.clicked.connect(self.pause_scan)
        self.ui.stopButton.clicked.connect(self.abort_scan)
        self.ui.fileOptionButton.clicked.connect(self.display_scan_data_options_dialog)

        self.ui.pauseButton.setEnabled(False)
        self.ui.stopButton.setEnabled(False)

        self.editing_new_plan = False
        self.editing_plan = False
        self.current_plan_index = 0

        self.scan_length = 0
        self.scan_start_at = datetime.now()
        self.scan_step = 0
        self.scan_paused = False
        self.frame_count_from_paused = 0
        self.scanning = False

        self.ui.progressBar.setMinimum(0)
        self.ui.progressBar.setMaximum(1)
        self.ui.progressBar.setValue(0)

        self.scan_status_timer = QTimer()
        self.scan_status_timer.timeout.connect(self.update_elapse)
        self.scan_status_timer.start(500)

        self.status_update_lock = QMutex()
        self.update_status_sig.connect(self._scan_status_update)

        self.populate_plan_combo()

        self.registered_data_callbacks = []

        for data in ["__scan_length", "__scan_step", "__scan_paused",
                     "__scan_ended"]:
            cbk = partial(self.scan_status_update, data)
            self.registered_data_callbacks.append(cbk)
            self.data_client.request_data(data, cbk)

    def create_new_plan_clicked(self):
        name, ok = QInputDialog.getText(self, "Create new plan", "Plan name:")
        if ok and name:
            self.ui.planComboBox.blockSignals(True)
            idx = self.ui.planComboBox.count()
            self.ui.planComboBox.insertItem(
                idx,
                name + "*",
                name
            )
            self.ui.planComboBox.setCurrentIndex(idx)
            self.current_plan_index = idx
            self.editing_new_plan = True
            self.reset_motor_detector_list()
            self.ui.planComboBox.blockSignals(False)

    def plan_changed(self):
        # item = self.ui.planComboBox.model().item(
        #     self.ui.planComboBox.currentIndex())
        # font = item.font()
        # font.setBold(True)
        # item.setFont(font)
        self.ui.planComboBox.setItemText(self.ui.planComboBox.currentIndex(),
                                         self.ui.planComboBox.currentData()
                                         + "*")
        self.editing_plan = True

    def populate_plan_combo(self):
        plans = self.scan_manager.listScanPlans()
        if plans:
            for plan in plans:
                self.ui.planComboBox.addItem(plan, plan)
                self.plan_combo_index_changed(
                    self.ui.planComboBox.currentIndex())
        else:
            self.add_motor()
            self.add_detector()

    def plan_combo_index_changed(self, index):
        if self.editing_new_plan or self.editing_plan:
            msgbox = QMessageBox()
            msgbox.setText("The plan has been modified.")
            msgbox.setInformativeText("Do you want to save the change?")
            msgbox.setStandardButtons(QMessageBox.Save | QMessageBox.Discard |
                                      QMessageBox.Cancel)
            ret = msgbox.exec()
            if ret == QMessageBox.Save:
                name = self.ui.planComboBox.itemData(self.current_plan_index)
                self.ui.planComboBox.setItemText(self.current_plan_index,
                                                 name)
                self.save_scan_plan()
            elif ret == QMessageBox.Cancel:
                self.ui.planComboBox.blockSignals(True)
                self.ui.planComboBox.setCurrentIndex(self.current_plan_index)
                self.ui.planComboBox.blockSignals(False)
                return
            else:  # Discard
                pass

        self.ui.planComboBox.setEnabled(False)
        self.populate_plan_inst(self.ui.planComboBox.itemData(index))
        self.current_plan_index = index
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
                    self.add_motor(device.name)
                    self.plan_changed()
            else:
                name_to_delete = self.ui.motorTableWidget.item(
                    row, MOTOR_NAME_COL).text()
                del self.scanned_motors[name_to_delete]
                del self.scan_data_options[name_to_delete]
                self.ui.motorTableWidget.removeRow(row)
                self.plan_changed()
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
                    self.add_detector(device.name)
                    self.plan_changed()
            else:
                name_to_delete = self.ui.detectorTableWidget.item(
                    row, DETECTOR_NAME_COL).text()
                self.scanned_detectors.remove(name_to_delete)
                del self.scan_data_options[name_to_delete]
                self.ui.detectorTableWidget.removeRow(row)
                self.plan_changed()
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
                self.plan_changed()
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
            self.scan_data_options[motor_id] = self.prepare_scan_data_option(motor_id)
            self.scanned_motors[motor_id] = MotorScanInstruction(
                name=motor_id,
                start=start,
                stop=stop,
                point_num=point_num
            )
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
            if not detector_id or detector_id in self.scanned_detectors:
                return
            self.scanned_detectors.append(detector_id)
            self.scan_data_options[detector_id] = self.prepare_scan_data_option(detector_id)
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
        self.scanned_motors = {}
        for row in reversed(range(self.ui.motorTableWidget.rowCount())):
            self.ui.motorTableWidget.removeRow(row)
        self.add_motor()
        self.ui.motorTableWidget.blockSignals(False)

        self.ui.detectorTableWidget.blockSignals(True)
        self.scanned_detectors = []
        self.scan_data_options = {}
        for row in reversed(range(self.ui.detectorTableWidget.rowCount())):
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
        if self.scan_paused:
            self.scan_manager.resumeScan()
        elif self.save_scan_plan():
            name = self.ui.planComboBox.currentText()
            self.ui.statusLabel.setText("PENDING")
            self.update_remote_scan_data_options()
            self.scan_manager.runScan(name)

    def update_remote_scan_data_options(self):
        result_sdos = []

        for dev, sdos in self.scan_data_options.items():
            for sdo in sdos:
                result_sdos.append(
                    ScanDataOption(
                        dev=dev,
                        name=sdo['name'],
                        save=sdo['save'],
                        single_file=sdo['single']
                    )
                )

        self.file_writer.updateScanDataOptions(result_sdos)

    def save_scan_plan(self):
        if not self.validate_plan_input():
            QMessageBox.warning(
                self,
                "Mamba",
                "Invalid values of scan parameters.\n",
                QMessageBox.Ok)
            return False
        name = self.ui.planComboBox.currentData()
        self.ui.planComboBox.setItemText(self.ui.planComboBox.currentIndex(),
                                         name)
        inst = ScanInstruction(
            motors=list(self.scanned_motors.values()),
            detectors=self.scanned_detectors
        )
        self.scan_manager.setScanPlan(name, inst)
        self.editing_plan = False
        self.editing_new_plan = False
        return True

    def prepare_scan_data_option(self, detector_id):
        data_descriptors: List[DataDescriptor] = \
            self.device_manager.describeDeviceReadings(detector_id)

        data_options = []
        for data_descriptor in data_descriptors:
            data_option = {
                'dev': detector_id,
                'name': data_descriptor.name,
                'type': data_descriptor.type,
                'save': True,
                'single': False
            }
            data_options.append(data_option)

        return data_options

    def display_scan_data_options_dialog(self):
        dialog = ScanFileOptionDialog()

        print(self.scan_data_options)

        scan_data_options = dialog.display(self.scan_data_options)

        for sdo in scan_data_options:
            for dev_sdo in self.scan_data_options[sdo['dev']]:
                if dev_sdo['name'] == sdo['name']:
                    dev_sdo.update(sdo)

        print(self.scan_data_options)

    def scan_status_update(self, name, scan_id, value, timestamp):
        self.update_status_sig.emit(name, scan_id,
                                    value if value is not None else 0)

    def _scan_status_update(self, name, scan_id, value):
        if name == "__scan_length":
            if not self.scanning:
                self.scanning = True
                self.scan_paused = False
                self.ui.statusLabel.setText("RUNNING")
                self.ui.scanIDLabel.setText(str(scan_id))
                self.scan_length = 0
                self.scan_step = 0
                self.frame_count_from_paused = 0
                self.scan_start_at = datetime.now()
                self.ui.frameLabel.setText(f"-/-")
                self.ui.runButton.setEnabled(False)
                self.ui.stopButton.setEnabled(True)
                self.ui.pauseButton.setEnabled(True)
                return

            self.scan_length = int(value)
            self.ui.progressBar.setMaximum(self.scan_length)
        elif name == "__scan_ended":
            self.ui.statusLabel.setText("IDLE")
            self.scanning = False
            self.ui.runButton.setEnabled(True)
            self.ui.stopButton.setEnabled(False)
            self.ui.pauseButton.setEnabled(False)
            return
        elif name == "__scan_paused":
            if value:
                if value == PAUSED:
                    self.scan_paused = True
                    self.ui.runButton.setEnabled(True)
                    self.ui.pauseButton.setEnabled(False)
                    self.ui.statusLabel.setText("PAUSED")
                elif value == RESUMED:
                    self.frame_count_from_paused = 0
                    self.scan_start_at = datetime.now()
                    self.scan_paused = False
                    self.ui.runButton.setEnabled(False)
                    self.ui.pauseButton.setEnabled(True)
                    self.ui.statusLabel.setText("RUNNING")

        elif name == "__scan_step":
            if value is None:
                return
            self.frame_count_from_paused += 1
            self.scan_step = int(value)
            self.ui.progressBar.setValue(self.scan_step)
            self.ui.frameLabel.setText(f"{self.scan_step}/{self.scan_length}")

    def update_elapse(self):
        if self.scanning and not self.scan_paused:
            elapsed = datetime.now() - self.scan_start_at
            self.ui.elapsedLabel.setText(self.convert_to_time(elapsed))
            time_per_frame = elapsed / self.frame_count_from_paused
            eta = time_per_frame * (self.scan_length - self.scan_step)
            self.ui.etaLabel.setText(self.convert_to_time(eta))
        else:
            self.ui.elapsedLabel.setText("0:00:00")

    def pause_scan(self):
        self.scan_manager.pauseScan()

    def abort_scan(self):
        self.scan_manager.terminateScan()

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
        if text is None:
            text = ""
        item = QTableWidgetItem()
        item.setText(str(text))
        return item

    @staticmethod
    def convert_to_time(delta: timedelta):
        seconds = int(delta.total_seconds())
        hours = int(seconds / 3600)
        mins = int((seconds % 3600) / 60)
        seconds = int((seconds % 3600) % 60)
        return f"{hours}:{mins:02d}:{seconds:02d}"

    @classmethod
    def get_init_func(cls, device_manager: DeviceManagerPrx,
                      scan_manager: ScanManagerPrx,
                      data_client: DataClientI,
                      file_writer: FileWriterHostPrx):
        return lambda: cls(device_manager, scan_manager, data_client, file_writer)

    def __del__(self):
        for cbk in self.registered_data_callbacks:
            self.data_client.stop_requesting_data(cbk)



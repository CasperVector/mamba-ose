import os
import yaml
from datetime import datetime, timedelta
from collections import namedtuple

from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QMessageBox, QInputDialog
from PyQt5.QtGui import QIcon, QColor, QPixmap, QBrush
from PyQt5.QtCore import Qt, QSize, QTimer, QMutex, pyqtSignal

from ..dialogs.device_select import DeviceSelectDialog
from ..dialogs.device_config import DeviceConfigDialog
from ..dialogs.metadata_generator import MetadataGenerator
from .ui_scanmechanismwidget import Ui_ScanMechanicsWidget

MOTOR_ADD_COL = 0
MOTOR_NAME_COL = 1
MOTOR_SETUP_COL = 2
MOTOR_START_COL = 3
MOTOR_END_COL = 4
MOTOR_NUM_COL = 5

DETECTOR_ADD_COL = 0
DETECTOR_NAME_COL = 1
DETECTOR_SETUP_COL = 2

MotorScanInstruction = namedtuple("MotorScanInstruction",
    ["name", "start", "stop", "point_num"])
ScanInstruction = namedtuple("ScanInstruction", ["motors", "detectors"])

class ScanManager(object):
    def __init__(self, mrc, plan_dir):
        self.mrc = mrc
        self.plan_dir = plan_dir
        self.plans = {}
        self.load_all_plans()

    def load_all_plans(self):
        if not os.path.exists(self.plan_dir):
            os.mkdir(self.plan_dir)
            return

        files = filter(lambda s: s.endswith(".yaml") and s.startswith("plan_"),
                       os.listdir(self.plan_dir))
        for file in files:
            try:
                with open(os.path.join(self.plan_dir, file), "r") as f:
                    plan_dic = yaml.safe_load(f)
                    motors = [MotorScanInstruction(
                        name=mot['name'],
                        start=float(mot['start']),
                        stop=float(mot['stop']),
                        point_num=int(mot['point_num'])
                    ) for mot in plan_dic['motors']]
                    self.plans[plan_dic['name']] = ScanInstruction(
                        motors=motors,
                        detectors=plan_dic['detectors']
                    )
            except (OSError, KeyError):
                continue

    def save_plan(self, name, instruction):
        file = "plan_" + name + ".yaml"
        with open(os.path.join(self.plan_dir, file), "w") as f:
            plan_dic = {
                'name': name,
                'detectors': instruction.detectors,
                'motors': [
                    {
                        'name': mot.name,
                        'start': mot.start,
                        'stop': mot.stop,
                        'point_num': mot.point_num
                     } for mot in instruction.motors
                ]
            }
            yaml.safe_dump(plan_dic, f)

    @staticmethod
    def generate_scan_command(plan):
        dets = [f'{name}' for name in plan.detectors]
        det_str = str(dets).replace("'", "")
        command = f"RE(grid_scan({det_str},\x11\n"
        for motor in plan.motors:
            command += f"{motor.name}, {float(motor.start)}, " \
                       f"{float(motor.stop)}, {int(motor.point_num)},\x11\n"
        command = command[:-2] + " progress = U.progress"
        command += "),\x11\nmd = U.mdg.read_advance())\n"
        return command

    def run_scan_plan(self, plan):
        self.mrc.req_rep_base("cmd", go = "",
            cmd = self.generate_scan_command(plan))

    def getScanPlan(self, name):
        if name in self.plans:
            return self.plans[name]

    def listScanPlans(self):
        return list(self.plans.keys())

    def setScanPlan(self, name, instruction):
        self.plans[name] = instruction
        self.save_plan(name, instruction)

    def runScan(self, name):
        self.run_scan_plan(self.plans[name])

    def pauseScan(self):
        self.mrc.req_rep("scan/pause")

    def resumeScan(self):
        self.mrc.req_rep("scan/resume")

    def terminateScan(self):
        self.mrc.req_rep("scan/abort")

class ScanMechanismWidget(QWidget):
    def __init__(self, mrc, mnc, config):
        super().__init__()
        self.scan_manager = ScanManager(mrc,
            os.path.expanduser(config['scan']['plans']))
        self.mrc = mrc
        self.mnc = mnc

        self.scanned_motors = {}
        self.scanned_detectors = []

        self.ui = Ui_ScanMechanicsWidget()
        self.ui.setupUi(self)

        for btn, (pix, size) in [
            (self.ui.runButton, (QPixmap(":/playback-play.png"), 32)),
            (self.ui.pauseButton, (QPixmap(":/playback-pause.png"), 32)),
            (self.ui.stopButton, (QPixmap(":/playback-stop.png"), 32)),
            (self.ui.addPlanButton, (QPixmap(":/new-document.png"), 0)),
            (self.ui.savePlanButton, (QPixmap(":/save.png"), 32))
        ]:
            icon = QIcon(pix)
            btn.setIcon(icon)
            if size > 0:
                btn.setIconSize(QSize(size, size))

        self.setting_icon = QIcon(":/settings.png")
        self.add_icon = QIcon(":/list-add.png")
        self.remove_icon = QIcon(":/list-remove.png")

        self.ui.motorTableWidget.itemClicked.connect(self.motor_table_clicked)
        self.ui.motorTableWidget.itemChanged.connect(self.motor_table_changed)
        self.ui.detectorTableWidget.itemClicked.connect(self.detector_table_clicked)
        self.ui.runButton.clicked.connect(self.run)
        self.ui.savePlanButton.clicked.connect(self.save_scan_plan)
        self.ui.planComboBox.currentIndexChanged.connect(self.plan_combo_index_changed)
        self.ui.addPlanButton.clicked.connect(self.create_new_plan_clicked)
        self.ui.pauseButton.clicked.connect(self.pause_scan)
        self.ui.stopButton.clicked.connect(self.abort_scan)
        self.ui.mdgButton.clicked.connect(self.display_mdg_dialog)

        self.ui.pauseButton.setEnabled(False)
        self.ui.stopButton.setEnabled(False)

        self.editing_new_plan = False
        self.editing_plan = False
        self.current_plan_index = 0

        self.scan_start_at = datetime.now()
        self.scan_eta = None
        self.scan_paused = False
        self.scanning = False

        self.scan_status_timer = QTimer()
        self.scan_status_timer.timeout.connect(self.update_elapse)
        self.scan_status_timer.start(500)

        self.populate_plan_combo()
        self.mnc.subscribe("scan", self.scan_status_update)

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
                dialog = DeviceSelectDialog(self, "M",
                    self.scanned_motors.keys())
                device = dialog.display()
                if device:
                    self.add_motor(device)
                    self.plan_changed()
            else:
                name_to_delete = self.ui.motorTableWidget.item(
                    row, MOTOR_NAME_COL).text()
                del self.scanned_motors[name_to_delete]
                self.ui.motorTableWidget.removeRow(row)
                self.plan_changed()
        elif col == MOTOR_SETUP_COL:
            if row < self.ui.motorTableWidget.rowCount() - 1:
                name = self.ui.motorTableWidget.item(row,
                                                     MOTOR_NAME_COL).text()
                dialog = DeviceConfigDialog(name, self.mrc, self)
                dialog.show()

    def detector_table_clicked(self, item):
        row = self.ui.detectorTableWidget.row(item)
        col = self.ui.detectorTableWidget.column(item)

        if col == DETECTOR_ADD_COL:
            if row == self.ui.detectorTableWidget.rowCount() - 1:
                dialog = DeviceSelectDialog(self, "DM",
                    self.scanned_detectors)
                device = dialog.display()
                if device:
                    self.add_detector(device)
                    self.plan_changed()
            else:
                name_to_delete = self.ui.detectorTableWidget.item(
                    row, DETECTOR_NAME_COL).text()
                self.scanned_detectors.remove(name_to_delete)
                self.ui.detectorTableWidget.removeRow(row)
                self.plan_changed()
        elif col == DETECTOR_SETUP_COL:
            if row < self.ui.detectorTableWidget.rowCount() - 1:
                name = self.ui.detectorTableWidget.item(
                    row, DETECTOR_NAME_COL).text()
                dialog = DeviceConfigDialog(name, self.mrc, self)
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
                    self.scanned_motors[name] = \
                        self.scanned_motors[name]._replace(start = num)
                elif col == MOTOR_END_COL:
                    self.scanned_motors[name] = \
                        self.scanned_motors[name]._replace(stop = num)
                elif col == MOTOR_NUM_COL:
                    self.scanned_motors[name] = \
                        self.scanned_motors[name]._replace(point_num = num)
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
            self.scan_manager.runScan(name)

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

    def display_mdg_dialog(self):
        MetadataGenerator(self.mrc, self).exec_()

    def scan_status_update(self, msg):
        name = msg["typ"][1]
        if name == "start":
            self.scanning = True
            self.scan_paused = False
            self.ui.statusLabel.setText("RUNNING")
            self.ui.scanIDLabel.setText(str(msg["id"]))
            self.scan_start_at = datetime.now()
            self.ui.progress.setText("0%")
            self.ui.runButton.setEnabled(False)
            self.ui.stopButton.setEnabled(True)
            self.ui.pauseButton.setEnabled(True)
        elif name == "stop":
            self.ui.statusLabel.setText("IDLE")
            self.scanning = False
            self.ui.runButton.setEnabled(True)
            self.ui.stopButton.setEnabled(False)
            self.ui.pauseButton.setEnabled(False)
        elif name == "pause":
            self.scan_paused = True
            self.ui.runButton.setEnabled(True)
            self.ui.pauseButton.setEnabled(False)
            self.ui.statusLabel.setText("PAUSED")
        elif name == "resume":
            self.scan_start_at = datetime.now()
            self.scan_paused = False
            self.ui.runButton.setEnabled(False)
            self.ui.pauseButton.setEnabled(True)
            self.ui.statusLabel.setText("RUNNING")
        elif name == "progress":
            self.ui.progress.setText("%d%%" % round(100 * msg["progress"]))
            if msg["eta"] is not None:
                self.scan_eta = datetime.fromtimestamp(msg["eta"])

    def update_elapse(self):
        if self.scanning and not self.scan_paused:
            elapsed = datetime.now() - self.scan_start_at
            self.ui.elapsedLabel.setText(self.convert_to_time(elapsed))
            if self.scan_eta is None:
                self.ui.etaLabel.setText("N/A")
            else:
                eta = self.scan_eta - datetime.now()
                self.ui.etaLabel.setText(self.convert_to_time(eta))
        else:
            self.ui.progress.setText("0%")
            self.ui.elapsedLabel.setText("0:00:00")
            self.ui.etaLabel.setText("N/A")

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


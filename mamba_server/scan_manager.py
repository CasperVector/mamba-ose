import os
from typing import List
import yaml
import time

import Ice
import MambaICE
import mamba_server
from mamba_server.terminal_host import TerminalHostI
from mamba_server.data_router import (DataClientCallback, DataProcessor,
                                      DataRouterI)
from utils.data_utils import (TypedDataFrame, DataDescriptor, DataType,
                              to_data_frame)
from utils import general_utils

if hasattr(MambaICE.Dashboard, 'ScanManager') and \
        hasattr(MambaICE.Dashboard, 'MotorScanInstruction') and \
        hasattr(MambaICE.Dashboard, 'ScanInstruction') and \
        hasattr(MambaICE.Dashboard, 'ScanExitStatus') and \
        hasattr(MambaICE.Dashboard, 'UnauthorizedError'):
    from MambaICE.Dashboard import (ScanManager, MotorScanInstruction,
                                    ScanInstruction, ScanExitStatus,
                                    UnauthorizedError)
else:
    from MambaICE.dashboard_ice import (ScanManager, MotorScanInstruction,
                                        ScanInstruction, ScanExitStatus,
                                        UnauthorizedError)

if hasattr(MambaICE.Experiment, 'ScanControllerPrx'):
    from MambaICE.Experiment import ScanControllerPrx
else:
    from MambaICE.experiment_ice import ScanControllerPrx


client_verify = mamba_server.verify

PAUSED = 1
RESUMED = 2


class ScanManagerI(ScanManager):

    class ScanStatusDataCallback(DataClientCallback):
        def __init__(self, parent):
            self.parent = parent

        def scan_start(self, _id, data_descriptors):
            self.parent.scan_started(_id)

        def data_update(self, frames):
            pass

        def scan_end(self, status):
            self.parent.scan_ended()

    class ScanStatusDataProcessor(DataProcessor):
        def __init__(self, parent):
            self.parent = parent
            self.reset()

        def process_data_descriptors(self, _id, keys: List[DataDescriptor])\
                -> List[DataDescriptor]:
            self.start_at = time.time()
            return keys

        def process_data(self, frames: List[TypedDataFrame])\
                -> List[TypedDataFrame]:
            self.current_step += 1
            frames.append(
                to_data_frame("__scan_length", DataType.Integer, self.scan_length,
                              self.start_at))
            frames.append(
                to_data_frame("__scan_step", DataType.Integer, self.current_step,
                              time.time()))
            return frames

        def scan_start(self, length):
            self.scan_length = length

        def reset(self):
            self.scan_length = 0
            self.current_step = 0
            self.start_at = 0

    def __init__(self, plan_dir, communicator: Ice.Communicator,
                 terminal: TerminalHostI,
                 data_router: DataRouterI):
        self.logger = mamba_server.logger
        self.terminal = terminal
        self.data_router = data_router
        self.communicator = communicator
        self.plan_dir = plan_dir
        self._scan_controller = None
        self.plans = {}

        self.scan_status_processor = ScanManagerI.ScanStatusDataProcessor(self)
        self.data_router.append_data_processor(self.scan_status_processor)
        self.scan_status_callback = ScanManagerI.ScanStatusDataCallback(self)
        self.data_router.local_register_client("ScanStatusCallback",
                                               self.scan_status_callback)

        self.scan_running = False
        self.scan_paused = False
        self.ongoing_scan_id = -1

        self.load_all_plans()

    @property
    def scan_controller(self):
        if not self._scan_controller:
            self._scan_controller = ScanControllerPrx.checkedCast(
                self.communicator.stringToProxy(
                    f"ScanController:{self.terminal.get_slave_endpoint()}")
            )
        return self._scan_controller

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
                    self.logger.info(f"Scan plan loaded: {plan_dic['name']}")
            except (OSError, KeyError):
                continue

    def save_plan(self, name, instruction: ScanInstruction):
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
    def calculate_scan_steps(plan: ScanInstruction):
        length = 1
        for mot in plan.motors:
            length *= mot.point_num

        return length

    @staticmethod
    def generate_scan_command(plan: ScanInstruction):
        commands = []
        dets = [f'dets.{name}' for name in plan.detectors]
        det_str = str(dets).replace("'", "")
        command = ""
        if len(plan.motors) > 1:
            commands.append("from bluesky.plans import grid_scan")
            command += f"RE(grid_scan({det_str},\n"
        else:
            commands.append("from bluesky.plans import scan")
            command += f"RE(scan({det_str},\n"

        for motor in plan.motors:
            command += f"motors.{motor.name}, {float(motor.start)}, " \
                       f"{float(motor.stop)}, {int(motor.point_num)},\n"

        command = command[:-2]
        command += "))"

        commands.append(command)

        return commands

    def scan_started(self, _id):
        if self.scan_running:
            self.ongoing_scan_id = _id

    def scan_ended(self):
        self.scan_status_processor.reset()
        self.scan_running = False
        self.ongoing_scan_id = -1

    def run_scan_plan(self, plan: ScanInstruction):
        if not self.scan_running:
            self.scan_running = True
            self.scan_paused = False
            self.scan_status_processor.scan_start(
                self.calculate_scan_steps(plan))
            for cmd in self.generate_scan_command(plan):
                self.terminal.emitCommand(cmd)
        else:
            raise RuntimeError("There's other scan running at this moment.")

    @client_verify
    def getScanPlan(self, name, current=None) -> ScanInstruction:
        if name in self.plans:
            return self.plans[name]

    @client_verify
    def listScanPlans(self, current=None) -> List[str]:
        return list(self.plans.keys())

    @client_verify
    def setScanPlan(self, name, instruction, current=None):
        self.plans[name] = instruction
        self.save_plan(name, instruction)

    @client_verify
    def runScan(self, name, current=None):
        self.run_scan_plan(self.plans[name])

    @client_verify
    def pauseScan(self, current=None):
        if self.scan_running and not self.scan_paused:
            self.scan_paused = True
            self.scan_controller.pause()
            self.data_router.get_recv_interface().pushData(
                [to_data_frame("__scan_paused", DataType.Integer, PAUSED, time.time())])

    @client_verify
    def resumeScan(self, current=None):
        if self.scan_paused:
            self.data_router.get_recv_interface().pushData(
                [to_data_frame("__scan_paused", DataType.Integer, RESUMED, time.time())])
            self.terminal.emitCommand("RE.resume()")
            self.scan_paused = False

    @client_verify
    def terminateScan(self, current=None):
        self.scan_running = False
        self.scan_controller.abort()
        #self.data_router.scanEnd(ScanExitStatus.Abort)


def initialize(communicator, adapter,
               terminal: TerminalHostI,
               data_router: DataRouterI):
    mamba_server.scan_manager = ScanManagerI(
        mamba_server.config['scan']['plan_storage'],
        communicator,
        terminal,
        data_router
    )

    adapter.add(mamba_server.scan_manager,
                communicator.stringToIdentity("ScanManager"))

    mamba_server.logger.info("ScanManager initialized.")

import os
import yaml

import Ice
import MambaICE
import mamba_server
from mamba_server.terminal_host import TerminalHostI
from mamba_server.data_router import DataClientCallback, DataRouterI

if hasattr(MambaICE.Dashboard, 'ScanManager') and \
        hasattr(MambaICE.Dashboard, 'MotorScanInstruction') and \
        hasattr(MambaICE.Dashboard, 'ScanInstruction') and \
        hasattr(MambaICE.Dashboard, 'UnauthorizedError'):
    from MambaICE.Dashboard import (ScanManager, MotorScanInstruction,
                                    ScanInstruction, UnauthorizedError)
else:
    from MambaICE.dashboard_ice import (ScanManager, MotorScanInstruction,
                                        ScanInstruction, UnauthorizedError)

if hasattr(MambaICE.Experiment, 'ScanControllerPrx'):
    from MambaICE.Experiment import ScanControllerPrx
else:
    from MambaICE.experiment_ice import ScanControllerPrx

client_verify = mamba_server.verify


class ScanManagerI(ScanManager):

    class ScanMgrDataCbk(DataClientCallback):
        def __init__(self, parent):
            self.parent = parent

        def scan_start(self, _id, data_descriptors):
            self.parent.scan_started(_id)

        def data_update(self, frames):
            pass

        def scan_end(self, status):
            self.parent.scan_ended()

    def __init__(self, storage_dir, communicator: Ice.Communicator,
                 host_ice_endpoint,
                 terminal: TerminalHostI,
                 data_router: DataRouterI):
        self.logger = mamba_server.logger
        self.storage_dir = storage_dir
        self.terminal = terminal
        self.data_router = data_router
        self.plans = {}

        self.scan_controller = ScanControllerPrx.checkedCast(
            self.communicator.stringToProxy(
                f"ScanController:{host_ice_endpoint}")
        )

        self.scan_running = False
        self.scan_paused = False
        self.ongoing_scan_id = -1

        self.load_all_plans()

    def load_all_plans(self):
        files = filter(lambda s: s.endswith(".yaml") and s.beginswith("plan_"),
                       os.listdir(self.storage_dir))
        for file in files:
            try:
                with open(os.path.join(self.storage_dir, file), "r") as f:
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
        with open(os.path.join(self.storage_dir, file), "w") as f:
            plan_dic = {
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

    def generate_scan_command(self, plan: ScanInstruction):
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

        for motor in self.motors:
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
        self.scan_running = False
        self.ongoing_scan_id = -1

    def run_scan_plan(self, plan: ScanInstruction):
        if not self.scan_running:
            self.scan_running = True
            self.scan_paused = False
            for cmd in self.generate_scan_command(plan):
                self.terminal.emitCommand(cmd)
        elif self.scan_paused:
            self.terminal.emitCommand("RE.resume()")
            self.scan_paused = False
        else:
            raise RuntimeError("There's other scan running at this moment.")

    @client_verify
    def getScanPlan(self, name, current=None) -> ScanInstruction:
        if name in self.plans:
            return self.plans[name]

    @client_verify
    def setScanPlan(self, name, instruction, current=None):
        self.plans[name] = instruction
        self.save_plan(name, instruction)

    @client_verify
    def runScan(self, name, current=None):
        self.run_scan_plan(self.plans[name])

    @client_verify
    def pauseScan(self, current=None):
        self.scan_controller.pause()

    @client_verify
    def terminateScan(self, current=None):
        self.scan_controller.halt()
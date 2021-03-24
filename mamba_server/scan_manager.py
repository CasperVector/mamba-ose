import base64
import pickle
import os
import yaml

import Ice
import MambaICE
import mamba_server

if hasattr(MambaICE.Dashboard, 'ScanManager') and \
        hasattr(MambaICE.Dashboard, 'MotorScanInstruction') and \
        hasattr(MambaICE.Dashboard, 'ScanInstruction'):
    from MambaICE.Dashboard import (ScanManager, MotorScanInstruction,
                                    ScanInstruction)
else:
    from MambaICE.dashboard_ice import (ScanManager, MotorScanInstruction,
                                        ScanInstruction)


def mzserver_callback(mzs):
    notify = mzs.notify
    def cb(name, doc):
        if name == "start":
            notify({"typ": "scan/start", "id": doc["scan_id"]})
        notify({"typ": "doc/" + name,
            "doc": base64.b64encode(pickle.dumps(doc)).decode("UTF-8")})
        if name == "stop":
            notify({"typ": "scan/stop"})
    return cb


class ScanManagerI(ScanManager):

    def __init__(self, plan_dir):
        self.logger = mamba_server.logger
        self.mrc = mamba_server.mrc
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
                    self.logger.info(f"Scan plan loaded: {plan_dic['name']}")
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
        commands = []
        dets = [f'dets.{name}' for name in plan.detectors]
        det_str = str(dets).replace("'", "")
        command = ""
        if len(plan.motors) > 1:
            commands.append("from bluesky.plans import grid_scan\n")
            command += f"RE(grid_scan({det_str},\n"
        else:
            commands.append("from bluesky.plans import scan\n")
            command += f"RE(scan({det_str},\n"

        for motor in plan.motors:
            command += f"motors.{motor.name}, {float(motor.start)}, " \
                       f"{float(motor.stop)}, {int(motor.point_num)},\n"

        command = command[:-2]
        command += "))\n"

        commands.append(command)

        return commands

    def run_scan_plan(self, plan):
        for cmd in self.generate_scan_command(plan):
            self.mrc.do_cmd(cmd)

    def getScanPlan(self, name, current=None):
        if name in self.plans:
            return self.plans[name]

    def listScanPlans(self, current=None):
        return list(self.plans.keys())

    def setScanPlan(self, name, instruction, current=None):
        self.plans[name] = instruction
        self.save_plan(name, instruction)

    def runScan(self, name, current=None):
        self.run_scan_plan(self.plans[name])

    def pauseScan(self, current=None):
        self.mrc.do_scan("pause")

    def resumeScan(self, current=None):
        self.mrc.do_scan("resume")

    def terminateScan(self, current=None):
        self.mrc.do_scan("abort")


def initialize(adapter):
    mamba_server.scan_manager = \
        ScanManagerI(mamba_server.config['scan']['plan_storage'])
    mamba_server.data_callback = mzserver_callback(mamba_server.mzs)
    adapter.add(mamba_server.scan_manager,
                Ice.stringToIdentity("ScanManager"))
    mamba_server.logger.info("ScanManager initialized.")

import MambaICE
import MambaICE.Experiment
from bluesky import RunEngine

if hasattr(MambaICE.Experiment, 'ScanController'):
    from MambaICE.Experiment import ScanController
else:
    from MambaICE.experiment_ice import ScanController


class ScanControllerI(ScanController):
    def __init__(self):
        self.RE = None

    def pause(self):
        self.RE.request_pause()

    def halt(self):
        self.RE.halt()


def initialize(communicator, adapter):
    import mamba_server.experiment_subproc
    scan_controller_obj = ScanControllerI()
    adapter.add(scan_controller_obj,
                communicator.stringToIdentity("ScanController"))
    mamba_server.experiment_subproc.scan_controller = scan_controller_obj

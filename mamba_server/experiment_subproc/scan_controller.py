import asyncio
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

    def pause(self, current=None):
        self.RE.request_pause()

    def abort(self, current=None):
        asyncio.run_coroutine_threadsafe(self.RE._abort_coro(""), loop=self.RE.loop)

    def halt(self, current=None):
        self.RE.halt()


def initialize(communicator, adapter):
    import mamba_server.experiment_subproc
    scan_controller_obj = ScanControllerI()
    adapter.add(scan_controller_obj,
                communicator.stringToIdentity("ScanController"))
    mamba_server.experiment_subproc.scan_controller_obj = scan_controller_obj

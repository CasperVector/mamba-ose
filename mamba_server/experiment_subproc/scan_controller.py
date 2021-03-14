import asyncio

class ScanControllerI(object):
    def __init__(self):
        self.RE = None

    def pause(self, current=None):
        self.RE.request_pause()

    def abort(self, current=None):
        asyncio.run_coroutine_threadsafe(self.RE._abort_coro(""), loop=self.RE.loop)

    def halt(self, current=None):
        self.RE.halt()

def initialize():
    import mamba_server.experiment_subproc
    scan_controller_obj = ScanControllerI()
    mamba_server.experiment_subproc.scan_controller_obj = scan_controller_obj

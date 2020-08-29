import struct
import logging

import Ice
from traitlets.config.loader import Config
from IPython.terminal.embed import InteractiveShellEmbed
from Dashboard import DataRouterPrx, DataDescriptor, DataFrame, DataType, \
    ScanExitStatus, DataClient, TerminalEventHandlerPrx

from bluesky.callbacks.core import CallbackBase, make_class_safe

from pyqterm import TerminalIO


class IPythonTerminalIO(TerminalIO):
    def __init__(self, cols: int, rows: int, event_hdl_endpoint,
                 event_hdl_token, logger):
        super().__init__(cols, rows, logger=logger)
        self.banner = ""

        self.event_hdl_endpoint = event_hdl_endpoint
        self.event_hdl_token = event_hdl_token

    def run_slave(self):
        self.logger.setLevel(logging.WARN)
        ice_props = Ice.createProperties()
        ice_props.setProperty("Ice.ACM.Close", "0")  # CloseOff
        ice_props.setProperty("Ice.ACM.Heartbeat", "3")  # HeartbeatAlways
        ice_props.setProperty("Ice.ACM.Timeout", "30")

        ice_init_data = Ice.InitializationData()
        ice_init_data.properties = ice_props

        with Ice.initialize(ice_init_data) as communicator:
            event_hdl = TerminalEventHandlerPrx.checkedCast(
                communicator.stringToProxy(
                    f"TerminalEventHandler:{self.event_hdl_endpoint}"))
            event_hdl.attach(self.event_hdl_token)

            data_router = DataRouterPrx.checkedCast(
                communicator.stringToProxy(
                    f"DataRouter:{self.event_hdl_endpoint}"))
            data_callback = DataDispatchCallback(data_router)

            while True:
                # Create ipython instance
                cfg = Config()
                ipshell = InteractiveShellEmbed(config=cfg)

                # Insert event hook
                ipshell.events.register('pre_run_cell',
                                        lambda info:
                                        event_hdl.enterExecution(info.raw_cell)
                                        )
                ipshell.events.register('post_run_cell',
                                        lambda result:
                                        event_hdl.leaveExecution(
                                            str(result.result))
                                        )

                banner = f"** Mamba's IPython shell, with bluesky integration" \
                         f"\n   RunEngine has been initialized as RE."


                self._run_ipshell(ipshell, banner, data_callback)

    @staticmethod
    def _run_ipshell(ipshell, banner, data_callback):
        # avoid polluting the rest of the scope
        # NOTE: prepare user environment here
        from bluesky import RunEngine
        RE = RunEngine({})
        RE.subscribe(data_callback)
        ipshell(banner)


class DataDispatchCallback(CallbackBase):
    def __init__(self, data_host: DataRouterPrx):
        super().__init__()
        self.data_host = data_host
        self.data_keys = {}
        self.scan_id = 0

    def start(self, doc):
        self.scan_id = doc['scan_id']

    def descriptor(self, doc):
        # TODO: process header, scan metadata, etc
        self.data_keys = keys = doc['data_keys']

        data_descriptors = {
            key: DataDescriptor(key,
                                self._to_type(des['dtype']),
                                des['shape']) for key, des in keys.items()
        }
        self.data_host.scanStart(self.scan_id, data_descriptors)

    def event(self, doc):
        data_frames = [
            DataFrame(key,
                      self._pack(self.data_keys[key]['dtype'], num),
                      doc['timestamps'][key]) for key, num in doc['data'].items()
        ]

        self.data_host.pushData(data_frames)

    def stop(self, doc):
        if doc['exit_status'] == 'success':
            self.data_host.scanEnd(ScanExitStatus.Success)
        elif doc['exit_status'] == 'abort':
            self.data_host.scanEnd(ScanExitStatus.Abort)
        elif doc['exit_status'] == 'fail':
            self.data_host.scanEnd(ScanExitStatus.Fail)

    @staticmethod
    def _to_type(string):
        if string == 'number':
            return DataType.Float
        elif string == 'string':
            return DataType.String

    @staticmethod
    def _pack(_type, value):
        if _type == 'number':
            return struct.pack("d", float(value))
        elif _type == 'string':
            return value.encode('utf-8')


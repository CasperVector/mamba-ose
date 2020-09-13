import os
import logging

import Ice
from traitlets.config.loader import Config
from IPython.terminal.embed import InteractiveShellEmbed
from MambaICE.Dashboard import TerminalEventHandlerPrx, DataRouterPrx

from pyqterm import TerminalIO

import mamba_server
from .data_dispatch_callback import DataDispatchCallback


###################################################################
# PLEASE BE WARNED THAT THIS FILE IS RUN IN A FORKED SUBPROCESS.  #
# DO NOT TRY TO INVOKE THINGS OUTSIDE THIS MODULE EXCEPT YOU KNOW #
# WHAT YOU ARE DOING.                                             #
###################################################################


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
                    f"TerminalEventHandler:{self.event_hdl_endpoint}")
                    .ice_connectionId("MambaExperimentSubproc")
            )
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

import Ice
import Dashboard
from traitlets.config.loader import Config
from IPython.terminal.embed import InteractiveShellEmbed

from pyqterm import TerminalIO


class IPythonTerminalIO(TerminalIO):
    def __init__(self, cols: int, rows: int, event_hdl_endpoint,
                 event_hdl_token, logger):
        super().__init__(cols, rows, logger=logger)
        self.banner = ""

        self.event_hdl_endpoint = event_hdl_endpoint
        self.event_hdl_token = event_hdl_token

    def run_slave(self):
        with Ice.initialize([]) as communicator:
            event_hdl = Dashboard.TerminalEventHandlerPrx.checkedCast(
                communicator.stringToProxy(
                    f"TerminalEventHandler:{self.event_hdl_endpoint}"))
            event_hdl.attach(self.event_hdl_token)

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

                banner = "** Mamba's IPython shell, with bluesky integration"
                ipshell(banner)

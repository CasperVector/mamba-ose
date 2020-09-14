import os
import logging
from importlib import import_module

import Ice
import MambaICE

if hasattr(MambaICE, 'DeviceType'):
    from MambaICE import DeviceType
else:
    from MambaICE.types_ice import DeviceType

if hasattr(MambaICE.Dashboard, 'TerminalEventHandlerPrx') and \
        hasattr(MambaICE.Dashboard, 'DataRouterPrx') and \
        hasattr(MambaICE.Dashboard, 'DeviceManagerPrx'):
    from MambaICE.Dashboard import (TerminalEventHandlerPrx, DataRouterPrx,
                                    DeviceManagerPrx)
else:
    from MambaICE.dashboard_ice import (TerminalEventHandlerPrx, DataRouterPrx,
                                        DeviceManagerPrx)

from pyqterm import TerminalIO

import utils
import mamba_server.experiment_subproc as experiment_subproc
import mamba_server
from .data_dispatch_callback import DataDispatchCallback
from mamba_server.experiment_subproc import device_query


###################################################################
# PLEASE BE WARNED THAT THIS FILE IS RUN IN A FORKED SUBPROCESS.  #
# DO NOT TRY TO INVOKE THINGS OUTSIDE THIS MODULE EXCEPT YOU KNOW #
# WHAT YOU ARE DOING.                                             #
###################################################################


def start_experiment_subprocess(host_endpoint, event_hdl_token):
    # ======== THIS IS THE ENTRY POINT OF THE SUBPROCESS ========
    # NOTE: For security reason, all file handler except stdin, stdout and
    #       stderr has been closed.

    config = mamba_server.config

    logger = experiment_subproc.logger = logging.getLogger()

    handler = logging.FileHandler(
        config['logging']['experiment_subproc_logfile'])
    formatter = logging.Formatter(
        "[%(asctime)s %(levelname)s] "
        "[%(filename)s:%(lineno)d] %(message)s"
    )
    handler.setFormatter(formatter)
    experiment_subproc.logger.addHandler(handler)

    logger.setLevel(logging.WARN)
    ice_props = Ice.createProperties()
    ice_props.setProperty("Ice.ACM.Close", "0")  # CloseOff
    ice_props.setProperty("Ice.ACM.Heartbeat", "3")  # HeartbeatAlways
    ice_props.setProperty("Ice.ACM.Timeout", "30")

    ice_init_data = Ice.InitializationData()
    ice_init_data.properties = ice_props

    with Ice.initialize(ice_init_data) as communicator:
        adapter = communicator.createObjectAdapterWithEndpoints(
            "ExperimentSubprocess",
            utils.get_experiment_subproc_endpoint()
        )
        device_query.initialize(communicator, adapter)
        adapter.activate()

        event_hdl = TerminalEventHandlerPrx.checkedCast(
            communicator.stringToProxy(
                f"TerminalEventHandler:{host_endpoint}")
                .ice_connectionId("MambaExperimentSubproc")
        )
        event_hdl.attach(event_hdl_token)

        data_router = DataRouterPrx.checkedCast(
            communicator.stringToProxy(f"DataRouter:{host_endpoint}")
                .ice_connectionId("MambaExperimentSubproc")
        )
        data_callback = DataDispatchCallback(data_router)

        experiment_subproc.device_manager = DeviceManagerPrx.checkedCast(
            communicator.stringToProxy(f"DeviceManager:{host_endpoint}")
                .ice_connectionId("MambaExperimentSubproc")
        )

        while True:
            from traitlets.config.loader import Config
            from IPython.terminal.embed import InteractiveShellEmbed

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

            _run_ipshell(ipshell, banner, data_callback)


def _run_ipshell(ipshell, banner, data_callback):
    # avoid polluting the rest of the scope
    # NOTE: prepare user environment here

    import mamba_server.experiment_subproc

    init_module = import_module('mamba_server.user_scripts.{:s}'.format(
        mamba_server.config['device']['init_module']
    ))
    if hasattr(init_module, "__registered_devices") and \
            isinstance(init_module.__registered_devices, dict):
        try:
            experiment_subproc.device_query_obj.load_devices(
                init_module.__registered_devices)
            experiment_subproc.device_query_obj.push_devices_to_host(
                experiment_subproc.device_manager
            )
            motors = utils.AttrDict(
                init_module.__registered_devices[DeviceType.Motor])
            dets = utils.AttrDict(
                init_module.__registered_devices[DeviceType.Detector])
        except KeyError:
            print("ERROR: Failed to load devices")
    else:
        print("ERROR: Failed to load devices")

    expose_everything_inside_module(init_module)

    from bluesky import RunEngine
    RE = RunEngine({})
    RE.subscribe(data_callback)
    ipshell(banner)


def expose_everything_inside_module(module):
    globals().update(
        {n: getattr(module, n) for n in module.__all__} if hasattr(module, '__all__')
        else
        {k: v for (k, v) in module.__dict__.items() if not k.startswith('_')
         })


class IPythonTerminalIO(TerminalIO):
    def __init__(self, cols: int, rows: int, host_endpoint,
                 event_hdl_token, logger):
        super().__init__(cols, rows, logger=logger)
        self.banner = ""
        self.logger = logger

        self.host_endpoint = host_endpoint
        self.event_hdl_token = event_hdl_token

    def run_slave(self):
        start_experiment_subprocess(self.host_endpoint, self.event_hdl_token)
        self.logger = experiment_subproc.logger

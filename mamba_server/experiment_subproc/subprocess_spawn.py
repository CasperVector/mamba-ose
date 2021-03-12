import Ice
import MambaICE

if hasattr(MambaICE, 'DeviceType'):
    from MambaICE import DeviceType
else:
    from MambaICE.types_ice import DeviceType

if hasattr(MambaICE.Dashboard, 'TerminalEventHandlerPrx') and \
        hasattr(MambaICE.Dashboard, 'DataRouterRecvPrx') and \
        hasattr(MambaICE.Dashboard, 'DeviceManagerInternalPrx'):
    from MambaICE.Dashboard import (TerminalEventHandlerPrx, DataRouterRecvPrx,
                                    DeviceManagerInternalPrx)
else:
    from MambaICE.dashboard_ice import (TerminalEventHandlerPrx, DataRouterRecvPrx,
                                        DeviceManagerInternalPrx)

from utils import general_utils
import mamba_server.experiment_subproc as experiment_subproc
import mamba_server
from mamba_server.experiment_subproc.data_dispatch_callback \
    import DataDispatchCallback
from mamba_server.experiment_subproc import device_query, scan_controller


def start_experiment_subprocess(host_endpoint):
    experiment_subproc.logger = mamba_server.logger

    ice_props = Ice.createProperties()
    ice_props.setProperty("Ice.ACM.Close", "0")  # CloseOff
    ice_props.setProperty("Ice.ACM.Heartbeat", "3")  # HeartbeatAlways
    ice_props.setProperty("Ice.ACM.Timeout", "30")

    ice_props.setProperty("Ice.MessageSizeMax", "100000")  # 100000KB ~ 100MB

    ice_init_data = Ice.InitializationData()
    ice_init_data.properties = ice_props

    communicator = Ice.initialize(ice_init_data)
    adapter = communicator.createObjectAdapterWithEndpoints(
        "ExperimentSubprocess",
        general_utils.format_endpoint("127.0.0.1", 0, "tcp")
    )
    experiment_subproc.slave_adapter = adapter

    device_query.initialize(communicator, adapter)
    scan_controller.initialize(communicator, adapter)
    adapter.activate()

    event_hdl = TerminalEventHandlerPrx.checkedCast(
        communicator.stringToProxy(
            f"TerminalEventHandler:{host_endpoint}").ice_connectionId("MambaExperimentSubproc")
    )
    event_hdl.ice_ping()

    event_hdl.attach(adapter.getEndpoints()[0].getInfo().port)

    data_router = DataRouterRecvPrx.checkedCast(
        communicator.stringToProxy(f"DataRouterRecv:{host_endpoint}").ice_connectionId("MambaExperimentSubproc")
    )
    data_router.ice_ping()
    experiment_subproc.data_callback = DataDispatchCallback(data_router)

    experiment_subproc.device_manager = DeviceManagerInternalPrx.checkedCast(
        communicator.stringToProxy(f"DeviceManagerInternal:{host_endpoint}")
            .ice_connectionId("MambaExperimentSubproc")
    )
    experiment_subproc.device_manager.ice_ping()


def post_start(RE, motors, dets):
    devices = {DeviceType.Motor: motors, DeviceType.Detector: dets}
    experiment_subproc.device_query_obj.load_devices(devices)
    experiment_subproc.device_query_obj.push_devices_to_host(
        experiment_subproc.device_manager
    )
    RE.subscribe(experiment_subproc.data_callback)
    experiment_subproc.scan_controller_obj.RE = RE
    return general_utils.AttrDict(motors), general_utils.AttrDict(dets)


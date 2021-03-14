import MambaICE

if hasattr(MambaICE, 'DeviceType'):
    from MambaICE import DeviceType
else:
    from MambaICE.types_ice import DeviceType

from utils import general_utils
import mamba_server.experiment_subproc as experiment_subproc
import mamba_server
from mamba_server.experiment_subproc.data_dispatch_callback \
    import DataDispatchCallback
from mamba_server.experiment_subproc import device_query, scan_controller


def start_experiment_subprocess():
    experiment_subproc.logger = mamba_server.logger
    device_query.initialize()
    scan_controller.initialize()
    experiment_subproc.data_callback = DataDispatchCallback(mamba_server.data_router)
    experiment_subproc.device_manager = mamba_server.device_manager.get_internal_interface()


def post_start(RE, motors, dets):
    devices = {DeviceType.Motor: motors, DeviceType.Detector: dets}
    experiment_subproc.device_query_obj.load_devices(devices)
    experiment_subproc.device_query_obj.push_devices_to_host(
        experiment_subproc.device_manager
    )
    RE.subscribe(experiment_subproc.data_callback)
    experiment_subproc.scan_controller_obj.RE = RE
    return general_utils.AttrDict(motors), general_utils.AttrDict(dets)


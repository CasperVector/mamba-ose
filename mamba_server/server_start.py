import os
import logging
import Ice
from .zserver import ZServer, ZrClient

import MambaICE
import mamba_server
import mamba_server.session_manager as session_manager
import mamba_server.data_router as data_router
import mamba_server.device_manager as device_manager
import mamba_server.scan_manager as scan_manager
from utils import general_utils

if hasattr(MambaICE, 'DeviceType'):
    from MambaICE import DeviceType
else:
    from MambaICE.types_ice import DeviceType

def server_start(RE, motors, dets):
    mamba_server.state = object()
    mamba_server.mzs = ZServer(5678, mamba_server.state)
    mamba_server.mzs.start()
    mamba_server.mrc = ZrClient(5678)

    # --- Ice properties setup ---
    public_ice_props = Ice.createProperties()

    # ACM setup for bidirectional connections.
    public_ice_props.setProperty("Ice.ACM.Close", "4")  # CloseOnIdleForceful
    public_ice_props.setProperty("Ice.ACM.Heartbeat", "0")  # HeartbeatOff
    public_ice_props.setProperty("Ice.ACM.Timeout", "30")

    public_ice_props.setProperty("Ice.MessageSizeMax", "10000")  # 10000KB ~ 10MB
    # Increase the thread pool, to handle nested RPC calls
    # If the thread pool is exhausted, new RPC call will block the mamba_server.
    # When a deadlock happens, one can use
    #    public_ice_props.setProperty("Ice.Trace.ThreadPool", "1")
    # to see the what's going on in the thread pool.
    # See https://doc.zeroc.com/ice/3.6/client-server-features/the-ice-threading-model/nested-invocations
    # for more information.
    public_ice_props.setProperty("Ice.ThreadPool.Client.Size", "1")
    public_ice_props.setProperty("Ice.ThreadPool.Client.SizeMax", "10")
    public_ice_props.setProperty("Ice.ThreadPool.Server.Size", "1")
    public_ice_props.setProperty("Ice.ThreadPool.Server.SizeMax", "10")

    pub_ice_init_data = Ice.InitializationData()
    pub_ice_init_data.properties = public_ice_props

    ic = Ice.initialize(pub_ice_init_data)
    mamba_server.logger = logger = logging.getLogger()

    if os.path.exists("server_config.yaml"):
        logger.info(f"Loading config file ./server_config.yaml")
        mamba_server.config_filename = "server_config.yaml"
    else:
        logger.warning("No config file discovered. Using the default one.")
        mamba_server.config_filename = general_utils.solve_filepath(
            "server_config.yaml", os.path.realpath(__file__))

    mamba_server.config = general_utils.load_config(
        mamba_server.config_filename)
    general_utils.setup_logger(logger, mamba_server.config['logging']['logfile'])

    public_endpoint = general_utils.get_bind_endpoint()
    mamba_server.logger.info(f"Server started. Bind at {public_endpoint}.")
    public_adapter = ic.createObjectAdapterWithEndpoints("MambaServer", public_endpoint)

    session_manager.initialize(public_adapter)
    data_router.initialize(public_adapter)
    device_manager.initialize(public_adapter)
    scan_manager.initialize(public_adapter, mamba_server.data_router)
    public_adapter.activate()

    devices = {DeviceType.Motor: motors, DeviceType.Detector: dets}
    mamba_server.device_query_obj.load_devices(devices)
    mamba_server.device_query_obj.push_devices_to_host(
        mamba_server.device_manager
    )
    RE.subscribe(mamba_server.data_callback)
    mamba_server.scan_controller_obj.RE = RE
    return general_utils.AttrDict(motors), general_utils.AttrDict(dets)


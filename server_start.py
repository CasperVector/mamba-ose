import sys
import logging
import Ice

import mamba_server
import mamba_server.session_manager as session_manager
import mamba_server.terminal_host as terminal
import mamba_server.data_router as data_router
import mamba_server.device_manager as device_manager
import utils

# --- Ice properties setup ---

ice_props = Ice.createProperties()

# ACM setup for bidirectional connections.
ice_props.setProperty("Ice.ACM.Close", "4")  # CloseOnIdleForceful
ice_props.setProperty("Ice.ACM.Heartbeat", "0")  # HeartbeatOff
ice_props.setProperty("Ice.ACM.Timeout", "30")

# Increase the thread pool, to handle nested RPC calls
# If the thread pool is exhausted, new RPC call will block the mamba_server.
# When a deadlock happens, one can use
#    ice_props.setProperty("Ice.Trace.ThreadPool", "1")
# to see the what's going on in the thread pool.
# See https://doc.zeroc.com/ice/3.6/client-server-features/the-ice-threading-model/nested-invocations
# for more information.
ice_props.setProperty("Ice.ThreadPool.Client.Size", "1")
ice_props.setProperty("Ice.ThreadPool.Client.SizeMax", "10")
ice_props.setProperty("Ice.ThreadPool.Server.Size", "1")
ice_props.setProperty("Ice.ThreadPool.Server.SizeMax", "10")

ice_init_data = Ice.InitializationData()
ice_init_data.properties = ice_props

with Ice.initialize(ice_init_data) as ic:
    mamba_server.communicator = ic
    mamba_server.logger = logger = logging.getLogger()

    mamba_server.config_filename = utils.solve_filepath("server_config.yaml")
    mamba_server.config = utils.load_config(mamba_server.config_filename)
    utils.setup_logger(logger)

    mamba_server.logger.info(f"Server started. Bind at {utils.get_bind_endpoint()}.")
    adapter = ic.createObjectAdapterWithEndpoints("HerosServer",
                                                  utils.get_bind_endpoint())

    session_manager.initialize(ic, adapter)
    terminal.initialize(ic, adapter)
    data_router.initialize(ic, adapter)
    device_manager.initialize(ic, adapter)

    adapter.activate()

    try:
        ic.waitForShutdown()
    except KeyboardInterrupt:
        pass

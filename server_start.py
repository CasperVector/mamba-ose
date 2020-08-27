import sys
import logging
import Ice

import server
import server.session_manager as session_manager
import server.terminal_host as terminal
import utils

ice_props = Ice.createProperties()
ice_props.setProperty("Ice.ACM.Close", "4")  # CloseOnIdleForceful
ice_props.setProperty("Ice.ACM.Heartbeat", "0")  # HeartbeatOff
ice_props.setProperty("Ice.ACM.Timeout", "30")

ice_init_data = Ice.InitializationData()
ice_init_data.properties = ice_props

with Ice.initialize(ice_init_data) as ic:
    server.logger = logger = logging.getLogger()

    server.config = utils.load_config("server_config.yaml")
    utils.setup_logger(logger)

    server.logger.info(f"Server started. Bind at {utils.get_bind_endpoint()}.")
    adapter = ic.createObjectAdapterWithEndpoints("HerosServer",
                                                  utils.get_bind_endpoint())

    session_manager.initialize(ic, adapter)
    terminal.initialize(ic, adapter)

    adapter.activate()

    try:
        ic.waitForShutdown()
    except KeyboardInterrupt:
        pass

import sys
import logging
import Ice

import server
import server.session_manager as session_manager
import server.terminal_host as terminal
import utils

with Ice.initialize(sys.argv) as ic:
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

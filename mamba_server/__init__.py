import logging

try:
    logger
except NameError:
    logger = logging.getLogger()

session_start_at = ""

logger = None
config = None

public_communicator = None
internal_communicator = None

public_adapter = None
internal_adapter = None

session = None
terminal = None
data_router = None
device_manager = None
file_writer_host = None
scan_manager = None

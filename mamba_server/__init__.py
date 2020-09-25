import logging

from .session_manager import verify

try:
    logger
except NameError:
    logger = logging.getLogger()

logger = None
config = None
communicator = None
session = None

terminal = None
terminal_con = None
data_router = None
device_manager = None
file_writer_host = None

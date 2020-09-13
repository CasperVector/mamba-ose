import logging

from .session_manager import verify
from .device_manager import DeviceType

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

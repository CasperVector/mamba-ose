import logging

try:
    logger
except NameError:
    logger = logging.getLogger()

logger = None
config = None
state = None
mzs = None
mrc = None

session = None
data_router = None
device_manager = None
scan_manager = None

data_callback = None
device_query_obj = None
scan_controller_obj = None


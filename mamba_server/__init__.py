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

device_manager = None
data_callback = None
device_query_obj = None


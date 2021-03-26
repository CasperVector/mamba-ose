import os
import yaml
import logging

class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self


def solve_filepath(path, my_path):
    if not path:
        return ''
    if path[0] == '/':
        return path
    else:
        mydir = os.path.dirname(my_path)
        return mydir + '/' + path

def load_config(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def setup_logger(logger, logfile=None, level=logging.INFO):
    logger.setLevel(level)
    if logfile:
        handler = logging.FileHandler(logfile)
    else:
        handler = logging.StreamHandler()
    formatter = logging.Formatter(
                "[%(asctime)s %(levelname)s] "
                "[%(filename)s:%(lineno)d] %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


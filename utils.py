# TODO: perhaps we need three utils: common_utils, client_utils, server_utils

import yaml
import logging

import mamba_client
import mamba_server


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self


def load_config(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def setup_logger(logger, level=logging.INFO):
    logger.setLevel(level)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
                "[%(asctime)s %(levelname)s] "
                "[%(filename)s:%(lineno)d] %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def format_endpoint(host, port, protocol='tcp'):
    if not protocol:
        protocol = 'tcp'

    endpoint = protocol
    if host:
        endpoint += " -h " + host

    endpoint += " -p " + str(port)

    return endpoint


def get_host_endpoint():
    return format_endpoint(
        mamba_client.config['network']['host_address'],
        mamba_client.config['network']['host_port'],
        mamba_client.config['network']['protocol']
    )


def get_bind_endpoint():
    return format_endpoint(
        mamba_server.config['network']['bind_address'],
        mamba_server.config['network']['bind_port'],
        mamba_server.config['network']['protocol']
    )


def get_access_endpoint():
    return format_endpoint(
        mamba_server.config['network']['access_address'],
        mamba_server.config['network']['bind_port'],
        mamba_server.config['network']['protocol']
    )

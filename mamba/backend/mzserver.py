import importlib
import os
import zmq
from .zserver import ZServer, ZnClient, ZrClient

def config_read(config = None):
    if config is None:
        config = os.getenv("MAMBACONFIG", "mamba_site.config")
    return importlib.import_module(config)

def server_build(globals, config, names = ["RE"], ctx = None):
    MzServer = type("MzServer", (ZServer,), {})
    U = type("MzState", (object,), {k: globals[k] for k in names})()
    U.mzs = MzServer(config.lport, U, globals, ctx)
    return U

def client_build_base(config, ctx = None):
    if not ctx:
        ctx = zmq.Context()
    MnClient = type("MnClient", (ZnClient,), {})
    MrClient = type("MrClient", (ZrClient,), {})
    mnc = MnClient(config.lport, ctx = ctx)
    return MrClient(config.lport, znc = mnc, ctx = ctx)

def client_build(config, *args, **kwargs):
    return config.client_build(config, *args, **kwargs)


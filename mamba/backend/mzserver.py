import importlib
import os
import re
import yaml
import zmq
from .zserver import ZServer, ZrClient, ZnClient, zcompose

def config_read(config = ""):
    if not config:
        config = os.path.expanduser("~/.mamba/config.yaml")
    with open(config, "r") as f:
        return yaml.safe_load(f)

def addons_find(paths):
    ret = []
    for mod, farg in [path.split(":") for path in paths]:
        f, arg = re.match(r"([^()]+)\(([^()]*)\)$", farg).groups()
        ret.append(getattr(importlib.import_module(mod), f)(arg))
    return ret

def addons_merge(addons):
    ret = {"mzs": {}, "mrc": {}, "mnc": {}, "state": []}
    for addon in addons:
        for k in ["mzs", "mrc", "mnc"]:
            if k in addon:
                ret[k].update(addon[k])
        if "state" in addon:
            build = addon["state"]
            meth = "extend" if isinstance(build, list) else "append"
            getattr(ret["state"], meth)(build)
    return ret

def server_start(globals, config):
    lport = int(config["backend"]["lport"])
    addon = addons_merge(addons_find(config["backend"]["saddons"]))
    MzServer = zcompose("MzServer", ZServer, addon["mzs"])
    U = type("MzState", (object,), {k: globals[k] for k in ["M", "D", "RE"]})()
    U.mzs = MzServer(lport, U, globals = globals)
    [build(U, config) for build in addon["state"]]
    U.mzs.start()
    return U

def client_build(config, ctx = None):
    addon = addons_merge(addons_find(config["backend"]["caddons"]))
    lport = int(config["backend"]["lport"])
    if not ctx:
        ctx = zmq.Context()
    MrClient = zcompose("MrClient", ZrClient, addon["mrc"])
    MnClient = zcompose("MnClient", ZnClient, addon["mnc"])
    mnc = MnClient(lport, ctx = ctx)
    return MrClient(lport, znc = mnc, ctx = ctx), mnc


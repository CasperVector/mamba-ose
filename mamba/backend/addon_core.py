import time
from butils.ophyd import DeviceLoader
from .zserver import ZChildHandler, ZError, \
    raise_syntax, unary_op, znc_handle_gen

class CoreZsHandler(ZChildHandler):
    handles = ["dev", "scan"]

    def do_dev(self, req):
        loader = self.parent.state.loader
        try:
            op, = req["typ"][1:]
            path = req["path"].split(".", 2)
            if op == "keys":
                assert len(path) == 1 and \
                    (path[0] == "C" or path[0] in loader.devs)
            else:
                assert len(path) > 1 and path[0] in loader.devs and \
                    op in ["prefix", "describe", "read",
                        "describe_configuration", "read_configuration"]
        except:
            raise_syntax(req)
        obj = loader.cpts if path[0] == "C" else loader.devs[path[0]]
        p = path[1:]
        try:
            while p:
                obj, p = getattr(obj, p[0]), p[1:]
            attr = getattr(obj, op)
        except:
            raise ZError("key", "invalid device")
        if op == "keys":
            prefix = "" if path[0] == "C" else path[0] + "."
            ret = [prefix + k for k in attr()]
        elif op == "prefix":
            ret = attr
        else:
            ret = attr(dot = True)
        return {"err": "", "ret": ret}

    def do_scan(self, req):
        parent, op = self.parent, unary_op(req)
        if op == "pause":
            parent.state.RE.request_pause()
            parent.notify({"typ": "scan/pause"})
        elif op == "resume":
            parent.notify({"typ": "scan/resume"})
            parent.do_cmd({"cmd": "RE.resume()\n", "go": ""})
        elif op == "abort":
            parent.state.RE.abort()
        else:
            raise_syntax(req)
        return {"err": ""}

class CoreZnHandler(ZChildHandler):
    handles = ["doc", "monitor", "scan"]
    do_doc = znc_handle_gen("doc")
    do_monitor = znc_handle_gen("monitor")
    do_scan = znc_handle_gen("scan")

def lossy_notify(periods, notify):
    timestamps, caches = {}, {}
    def lnotify(typ, doc):
        caches.setdefault(typ, {})
        for k, v in doc.items():
            if isinstance(v, dict):
                caches[typ].setdefault(k, {}).update(v)
            else:
                caches[typ][k] = v
        timestamp = time.monotonic()
        if timestamp < timestamps.get(typ, 0.0) + periods.get(typ, 0.0):
            return
        timestamps[typ] = timestamp
        doc, caches[typ] = caches[typ], {}
        notify({"typ": typ, "doc": doc})
    return lnotify

def mzserver_callback(notify):
    def cb(name, doc):
        if name == "start":
            notify({"typ": "scan/start", "id": doc["scan_id"]})
        notify({"typ": "doc/" + name, "doc": doc})
        if name == "stop":
            notify({"typ": "scan/stop"})
    return cb

def sextend_core(U, globals, config, devs = ["M", "D"]):
    assert "C" not in devs
    U.mzs.extend(CoreZsHandler())
    U.loader = DeviceLoader({d: globals[d] for d in devs})
    U.monitor_periods = {}
    U.lnotify = lossy_notify(U.monitor_periods, U.mzs.notify)
    U.mzcb = mzserver_callback(U.mzs.notify)
    globals["C"] = U.loader.cpts
    globals.update(U.loader.devs)

def cextend_core(mrc):
    mrc.znc.extend(CoreZnHandler())
    return mrc


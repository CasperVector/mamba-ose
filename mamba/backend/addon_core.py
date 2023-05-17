import base64
import pickle
import time
from .zserver import ZError, raise_syntax, unary_op, znc_handle_gen

def mzs_dev(self, req):
    try:
        op, = req["typ"][1:]
        path = req["path"].split(".", 2)
        if op == "keys":
            assert len(path) == 1
        else:
            assert len(path) > 1 and op in ["describe", "read",
                "describe_configuration", "read_configuration"]
        assert path[0] in ["M", "D"]
    except:
        raise_syntax(req)
    try:
        obj, p = self.state, path
        while p:
            obj, p = getattr(obj, p[0]), p[1:]
        f = getattr(obj, op)
    except:
        raise ZError("key", "invalid device")
    if op == "keys":
        prefix = path[0] + "."
        ret = [prefix + k for k in f()]
    else:
        ret = f(dot = True)
    return {"err": "", "ret": ret}

def mzs_scan(self, req):
    op = unary_op(req)
    RE = self.state.RE
    if op == "pause":
        RE.request_pause()
        self.notify({"typ": "scan/pause"})
    elif op == "resume":
        self.notify({"typ": "scan/resume"})
        self.do_cmd({"cmd": "RE.resume()\n", "go": ""})
    elif op == "abort":
        RE.abort()
    else:
        raise_syntax(req)
    return {"err": ""}

addonMzs = {"dev": mzs_dev, "scan": mzs_scan}

def doc_handle_gen(typ):
    def handler(self, msg):
        msg["doc"] = pickle.loads(base64.b64decode(msg["doc"].encode("UTF-8")))
        [sub(msg) for sub in self.subs[typ].values()]
    return handler

addonMnc = {
    "doc": doc_handle_gen("doc"),
    "monitor": doc_handle_gen("monitor"),
    "scan": znc_handle_gen("scan")
}

def doc_notify(notify):
    return lambda typ, doc: notify({"typ": typ, "doc":
        base64.b64encode(pickle.dumps(doc)).decode("UTF-8")})

def lossy_notify(periods, dnotify):
    timestamps, caches = {}, {}
    def lnotify(typ, doc):
        caches.setdefault(typ, {})
        for k, v in doc.items():
            if isinstance(v, dict):
                caches[typ].setdefault(k, {}).update(v)
            else:
                caches[typ][k] = v
        timestamp = time.time()
        if timestamp < timestamps.get(typ, 0.0) + periods.get(typ, 0.0):
            return
        timestamps[typ] = timestamp
        doc, caches[typ] = caches[typ], {}
        dnotify(typ, doc)
    return lnotify

def mzserver_callback(notify, dnotify):
    def cb(name, doc):
        if name == "start":
            notify({"typ": "scan/start", "id": doc["scan_id"]})
        dnotify("doc/" + name, doc)
        if name == "stop":
            notify({"typ": "scan/stop"})
    return cb

def state_build(U, config):
    U.dnotify, U.monitor_periods = doc_notify(U.mzs.notify), {}
    U.lnotify = lossy_notify(U.monitor_periods, U.dnotify)
    U.mzcb = mzserver_callback(U.mzs.notify, U.dnotify)

saddon_core = lambda arg: {"mzs": addonMzs, "state": state_build}
caddon_core = lambda arg: {"mnc": addonMnc}


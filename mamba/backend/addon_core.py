import base64
import pickle
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

def mnc_doc(self, msg):
    msg["doc"] = pickle.loads(base64.b64decode(msg["doc"].encode("UTF-8")))
    [sub(msg) for sub in self.subs["doc"].values()]

addonMnc = {"doc": mnc_doc, "scan": znc_handle_gen("scan")}

def mzserver_callback(mzs):
    notify = mzs.notify
    def cb(name, doc):
        if name == "start":
            notify({"typ": "scan/start", "id": doc["scan_id"]})
        notify({"typ": "doc/" + name,
            "doc": base64.b64encode(pickle.dumps(doc)).decode("UTF-8")})
        if name == "stop":
            notify({"typ": "scan/stop"})
    return cb

def state_build(U, config):
    U.mzcb = mzserver_callback(U.mzs)
    U.RE.subscribe(U.mzcb)

saddon_core = lambda arg: {"mzs": addonMzs, "state": state_build}
caddon_core = lambda arg: {"mnc": addonMnc}


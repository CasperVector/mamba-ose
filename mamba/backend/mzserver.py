import base64
import pickle
from traceback import print_exc
from .auth_md import MambaAuth, MambaMdGen
from .zserver import ZError, ZServer, ZrClient, ZnClient

def raise_syntax(typ):
    raise ZError("syntax", "invalid `%s' RPC" % typ)

class MzServer(ZServer):
    handles = ZServer.handles + ["dev", "scan", "auth", "md"]

    def do_dev(self, req):
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
            raise_syntax("dev")
        try:
            obj, p = self.state, path
            while p:
                obj, p = getattr(obj, p[0]), p[1:]
            f = getattr(obj, op)
        except:
            raise ZError("key", "improper device")
        if op == "keys":
            prefix = path[0] + "."
            ret = [prefix + k for k in f()]
        else:
            ret = f(dot = True)
        return {"err": "", "ret": ret}

    def do_scan(self, req):
        try:
            op, = req["typ"][1:]
        except:
            raise_syntax("scan")
        RE = self.state.RE
        if op == "pause":
            RE.request_pause()
            self.notify({"typ": "scan/pause"})
        elif op == "resume":
            self.notify({"typ": "scan/resume"})
            self.do_cmd({"cmd": "RE.resume()\n"})
        elif op == "abort":
            RE.abort()
        else:
            raise_syntax("scan")
        return {"err": ""}

    def do_auth(self, req):
        try:
            op, = req["typ"][1:]
        except:
            raise_syntax("auth")
        auth = self.state.auth
        if op == "pw":
            try:
                auth.pw = req["pw"]
                return {"err": ""}
            except:
                raise_syntax("auth")
        raise_syntax("auth")

    def do_md(self, req):
        try:
            op, = req["typ"][1:]
        except:
            raise_syntax("md")
        mdg = self.state.mdg
        if not mdg.mds[-1]["beamtimeId"]:
            raise ZError("deny", "not logged in")
        if op == "read":
            return {"err": "", "ret": mdg.read()}
        elif op == "read_private":
            return {"err": "", "ret": mdg.read_private()}
        raise_syntax("md")

class MrClient(ZrClient):
    do_dev = lambda self, op, path: \
        self.req_rep_chk("dev", op, path = path)["ret"]
    do_scan = lambda self, op: self.req_rep_chk("scan", op) and None
    do_auth = lambda self, op, **kwargs: self.req_rep_chk("auth", op, **kwargs)
    do_md = lambda self, op, **kwargs: self.req_rep_chk("md", op, **kwargs)

def non_fatal(f):
    def g(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except:
            print_exc()
    return g

class MnClient(ZnClient):
    handles = ZnClient.handles + ["doc", "scan"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.subs = {typ: {} for typ in self.handles}
        self.ids = {typ: -1 for typ in self.handles}

    def subscribe(self, typ, f):
        ids = self.ids
        ids[typ] += 1
        self.subs[typ][ids[typ]] = non_fatal(f)
        return ids[typ]

    def unsubscribe(self, typ, i):
        self.subs[typ].pop(i)

    def do_doc(self, msg):
        msg["doc"] = pickle.loads(base64.b64decode(msg["doc"].encode("UTF-8")))
        for sub in self.subs["doc"]:
            sub(msg)

    def do_scan(self, msg):
        for sub in self.subs["scan"]:
            sub(msg)

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

def server_start(M, D, RE, config = ""):
    import os, yaml
    if not config:
        config = os.path.expanduser("~/.mamba/config.yaml")
    with open(config, "r") as f:
        config = yaml.safe_load(f)
    lport = int(config["backend"]["lport"])
    U = type("MzState", (object,), {"M": M, "D": D, "RE": RE})()
    U.mdg = MambaMdGen()
    U.auth = MambaAuth(config["auth_md"], U.mdg)
    U.mzs = MzServer(lport, U, ipy = get_ipython())
    RE.subscribe(mzserver_callback(U.mzs))
    U.mzs.start()
    return U


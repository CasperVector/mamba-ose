import base64
import pickle
from .zserver import ZServer, ZrClient, ZnClient

class MzServer(ZServer):
    handles = ZServer.handles + ["scan"]

    def do_scan(self, req):
        try:
            op, = req["typ"][1:]
        except:
            return {"err": "syntax"}
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
            return {"err": "syntax"}
        return {"err": ""}

class MrClient(ZrClient):
    do_scan = lambda self, op: self.req_rep_chk("scan", op) and None

class MnClient(ZnClient):
    handles = ZnClient.handles + ["doc", "scan"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.subs = {typ: [] for typ in self.handles}

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


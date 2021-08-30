import json
import queue
import threading
import zmq

class ZError(Exception): pass

class ZServer(object):
    handles = ["cmd"]

    def __init__(self, lport, state, ctx = None, ipy = None):
        if not ctx:
            ctx = zmq.Context()
        self.lsock = ctx.socket(zmq.REQ)
        self.lsock.connect("tcp://127.0.0.1:%d" % lport)
        self.rsock = ctx.socket(zmq.REP)
        self.rsock.bind("tcp://127.0.0.1:%d" % (lport + 1))
        self.nlock = threading.Lock()
        self.nsock = ctx.socket(zmq.PUB)
        self.nsock.bind("tcp://127.0.0.1:%d" % (lport + 2))
        self.state = state
        self.q = None
        if ipy:
            ipy.events.register("post_run_cell", self.putter)

    def putter(self, result):
        if self.q:
            self.q.put({"ret": result.result,
                "err": result.error_before_exec or result.error_in_exec})

    def notify(self, msg):
        with self.nlock:
            return self.nsock.send_json(msg)

    def start(self):
        self.handles = {typ: getattr(self, "do_" + typ) for typ in self.handles}
        threading.Thread(target = self.loop, daemon = True).start()

    def loop(self):
        while True:
            try:
                req = self.rsock.recv_json()
                req["typ"] = req["typ"].split("/")
                typ = req["typ"][0]
            except:
                typ = None
            try:
                hdl = self.handles.get(typ)
                rep = hdl(req) if hdl else \
                    {"err": "syntax", "desc": "invalid ZServer RPC"}
            except Exception as e:
                if isinstance(e, ZError):
                    rep = {"err": e.args[0]}
                    if len(e.args) > 1:
                        rep["desc"] = e.args[1]
                else:
                    name, desc = type(e).__name__, str(e)
                    rep = {"err": "exc",
                        "desc": name + ": " + desc if desc else name}
            try:
                rep = json.dumps(rep).encode("UTF-8")
            except:
                rep = b'{"err": "json", ' + \
                    b'"desc": "error encoding ZServer response"}'
            try:
                self.rsock.send(rep)
            except: pass

    def do_cmd(self, req):
        try:
            cmd = req["cmd"].encode("UTF-8")
            wait = req.get("wait", True)
            assert isinstance(wait, bool)
        except:
            raise ZError("syntax", "invalid `cmd' RPC")
        if wait:
            self.q = queue.Queue()
        self.lsock.send(cmd)
        assert not self.lsock.recv()
        if wait:
            ret = self.q.get()
            self.q = None
            if ret["err"]:
                raise(ret["err"])
            ret = {"err": "", "ret": ret["ret"]}
        else:
            ret = {"err": ""}
        return ret

class ZrClient(object):
    def __init__(self, lport, ctx = None):
        if not ctx:
            ctx = zmq.Context()
        self.rsock = ctx.socket(zmq.REQ)
        self.rsock.connect("tcp://127.0.0.1:%d" % (lport + 1))

    def req_rep(self, typ, op = None, **kwargs):
        req = {"typ": typ + "/" + op if op else typ}
        req.update(kwargs)
        self.rsock.send_json(req)
        return self.rsock.recv_json()

    def req_rep_chk(self, typ, op = None, **kwargs):
        rep = self.req_rep(typ, op, **kwargs)
        if rep["err"]:
            name, desc = rep["err"], rep.get("desc", "")
            raise ZError("[%s]" % name + (desc and (" %s" % desc)))
        return rep

    do_cmd = lambda self, cmd, **kwargs: \
        self.req_rep_chk("cmd", cmd = cmd, **kwargs)

class ZnClient(object):
    handles = []

    def __init__(self, lport, ctx = None):
        if not ctx:
            ctx = zmq.Context()
        self.nsock = ctx.socket(zmq.SUB)
        self.nsock.subscribe("")
        self.nsock.connect("tcp://127.0.0.1:%d" % (lport + 2))

    def start(self):
        self.handles = {typ: getattr(self, "do_" + typ) for typ in self.handles}
        threading.Thread(target = self.loop, daemon = True).start()

    def loop(self):
        while True:
            try:
                msg = self.nsock.recv_json()
                msg["typ"] = msg["typ"].split("/")
                typ = msg["typ"][0]
            except:
                typ = None
            hdl = self.handles.get(typ)
            if hdl:
                hdl(msg)


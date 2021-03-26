import json
import threading
import zmq

class ZServer(object):
    handles = ["cmd"]

    def __init__(self, lport, state, ctx = None):
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
                rep = hdl(req) if hdl else {"err": "syntax"}
            except:
                rep = {"err": "handle"}
            try:
                rep = json.dumps(rep).encode("UTF-8")
            except:
                rep = {"err": "json"}
            try:
                self.rsock.send(rep)
            except: pass

    def do_cmd(self, req):
        try:
            cmd = req["cmd"].encode("UTF-8")
        except:
            return {"err": "syntax"}
        self.lsock.send(cmd)
        assert not self.lsock.recv()
        return {"err": ""}

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
        assert rep["err"] == "", rep["err"]
        return rep

    do_cmd = lambda self, cmd: self.req_rep_chk("cmd", cmd = cmd) and None

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


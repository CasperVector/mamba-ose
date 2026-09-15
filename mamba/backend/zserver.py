import queue
import re
import threading
import traceback
import uuid
import zmq
from butils.common import cbor_dump_numpy, cbor_load_numpy

class ZError(Exception): pass

class ZBaseHandler(object):
    handles = []

class ZChildHandler(ZBaseHandler):
    parent = None

class ZParentHandler(ZBaseHandler):
    def __init__(self):
        self.origins = [self]

    def extend(self, child):
        child.parent = self
        self.origins.append(child)
        self.make_handles()

    def make_handles(self):
        self._handles = {}
        # Insertion order preserved by dict() since Python 3.6.
        for obj in self.origins:
            self._handles.update\
                ({typ: getattr(obj, "do_" + typ) for typ in obj.handles})

    def start(self):
        threading.Thread(target = self.loop, daemon = True).start()

def non_fatal(f):
    def g(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except:
            traceback.print_exc()
    return g

def raise_syntax(req):
    raise ZError("syntax", "invalid `%s' RPC" % req["typ"][0])

def unary_op(req):
    try:
        op, = req["typ"][1:]
        return op
    except:
        raise_syntax(req)

def zsv_err_rep(e):
    if isinstance(e, ZError):
        rep = {"err": e.args[0]}
        if len(e.args) > 1:
            rep["desc"] = e.args[1]
    else:
        name, desc = type(e).__name__, str(e)
        rep = {"err": "exc", "desc":
            name + ": " + desc if desc else name}
    return rep

def zsv_rep_chk(rep):
    if rep["err"]:
        raise ZError(rep["err"], rep.get("desc", ""))
    return rep

def zsv_err_fmt(e):
    return "[%s]" % e.args[0] + (e.args[1] and (" %s" % e.args[1]))

class ZServer(ZParentHandler):
    handles = ["cmd"]

    def __init__(self, lport, state, globals, ctx = None):
        super().__init__()
        if not ctx:
            ctx = zmq.Context()
        self.lsock = ctx.socket(zmq.REQ)
        self.lsock.connect("tcp://127.0.0.1:%d" % lport)
        self.rsock = ctx.socket(zmq.REP)
        self.rsock.bind("tcp://127.0.0.1:%d" % (lport + 1))
        self.nlock = threading.Lock()
        self.nsock = ctx.socket(zmq.PUB)
        self.nsock.bind("tcp://127.0.0.1:%d" % (lport + 2))
        self.state, self.ipy = state, False
        self.q = self.uid = None
        self.make_handles()

        from IPython import get_ipython
        ipython = get_ipython()
        if ipython:
            from IPython.core.magic import register_line_cell_magic
            self.ipy = True
            def putter(result):
                rep = {"ret": result.result, "err":
                    result.error_before_exec or result.error_in_exec}
                if self.q:
                    self.q.put(rep)
                elif self.uid:
                    uid, self.uid = self.uid, None
                    self.notify({"typ": "go", "uid": str(uid), "rep": (
                        zsv_err_rep(rep["err"]) if rep["err"]
                        else {"err": "", "ret": rep["ret"]}
                    )})
            ipython.events.register("post_run_cell", putter)
            @register_line_cell_magic
            def go(line, cell = None):
                if cell:
                    line += "\n" + cell
                uid, note = (uuid.uuid4(), False) \
                    if self.uid is None else (self.uid, True)
                self.uid = None
                def inner():
                    try:
                        rep = {"err": "", "ret": eval(line, globals)}
                        print("%s: %s" % (uid, rep["ret"]))
                    except Exception as e:
                        rep = zsv_err_rep(e)
                        print("%s %s" % (uid, traceback.format_exc()), end = "")
                    if note:
                        self.notify({"typ": "go", "uid": str(uid), "rep": rep})
                threading.Thread(target = inner, daemon = True).start()
                return uid

    def notify(self, msg):
        with self.nlock:
            return self.nsock.send(cbor_dump_numpy(msg))

    def loop(self):
        while True:
            try:
                req = cbor_load_numpy(self.rsock.recv())
                req["typ"] = req["typ"].split("/")
                typ = req["typ"][0]
            except:
                typ = None
            try:
                hdl = self._handles.get(typ)
                rep = hdl(req) if hdl else \
                    {"err": "syntax", "desc": "invalid ZServer RPC"}
            except (Exception, KeyboardInterrupt) as e:
                rep = zsv_err_rep(e)
            try:
                rep = cbor_dump_numpy(rep)
            except:
                rep = cbor_dump_numpy({"err": "cbor",
                    "desc": "error encoding ZServer response"})
            try:
                self.rsock.send(rep)
            except: pass

    def get_state(self, req):
        return getattr(self.state, req["typ"][0])

    def do_cmd(self, req):
        try:
            cmd, uid = req["cmd"], req.get("go", None)
            doq = uid is None or bool(re.match(r"%%?go\b", cmd))
            cmd = cmd.encode("UTF-8")
            if uid is not None:
                assert self.ipy
                self.uid = uid = uuid.UUID(uid) if uid else uuid.uuid4()
        except:
            raise_syntax(req)
        if doq:
            self.q = queue.Queue()
        if cmd:
            self.lsock.send(cmd)
            assert not self.lsock.recv()
        if doq:
            ret = self.q.get()
            self.q = None
        if uid is None:
            if ret["err"]:
                raise(ret["err"])
            ret = {"err": "", "ret": ret["ret"]}
        else:
            if not cmd:
                self.uid = None
                self.notify({"typ": "go", "uid": str(uid),
                    "rep": {"err": "", "ret": None}})
            ret = {"err": ""}
        return ret

def znc_handle_gen(typ):
    return lambda self, msg: \
        [sub(msg) for sub in self.parent.subs[typ].values()]

class ZnClient(ZParentHandler):
    handles = ["go"]

    def __init__(self, lport, ctx = None):
        super().__init__()
        if not ctx:
            ctx = zmq.Context()
        self.nsock = ctx.socket(zmq.SUB)
        self.nsock.subscribe("")
        self.nsock.connect("tcp://127.0.0.1:%d" % (lport + 2))
        self.subs, self.ids = {}, {}
        self.make_handles()

    def make_handles(self):
        super().make_handles()
        for typ in self._handles:
            self.subs.setdefault(typ, {})
            self.ids.setdefault(typ, -1)

    def loop(self):
        while True:
            try:
                msg = cbor_load_numpy(self.nsock.recv())
                msg["typ"] = msg["typ"].split("/")
                typ = msg["typ"][0]
            except:
                typ = None
            hdl = self._handles.get(typ)
            if hdl:
                hdl(msg)

    def subscribe(self, typ, f):
        ids = self.ids
        ids[typ] += 1
        self.subs[typ][ids[typ]] = non_fatal(f)
        return ids[typ]

    def unsubscribe(self, typ, i):
        self.subs[typ].pop(i)

    do_go = lambda self, msg: [sub(msg) for sub in self.subs["go"].values()]

class ZStatus(object):
    def __init__(self, zrc, uid):
        self.zrc, self.uid, self.q = zrc, uid, queue.Queue()
        self.cb = self.rep = None
        with self.zrc.slock:
            self.zrc.status[uid] = self

    def done(self, rep):
        with self.zrc.slock:
            self.zrc.status.pop(self.uid)
            self.rep = rep
        if self.cb:
            self.cb(rep)
        self.q.put(None)

    def subscribe(self, cb):
        with self.zrc.slock:
            if not self.rep:
                self.cb = cb
                return
        cb(self.rep)

    def wait(self, timeout = None):
        self.q.get(timeout = timeout)
        return zsv_rep_chk(self.rep)

class ZrClient(object):
    def __init__(self, lport, znc = None, ctx = None):
        self.znc = znc
        if znc:
            self.status, self.slock = {}, threading.Lock()
            def sub(msg):
                st = self.status.get(uuid.UUID(msg["uid"]))
                if st:
                    st.done(msg["rep"])
            znc.subscribe("go", sub)
        if not ctx:
            ctx = zmq.Context()
        self.rlock = threading.Lock()
        self.rsock = ctx.socket(zmq.REQ)
        self.rsock.connect("tcp://127.0.0.1:%d" % (lport + 1))

    def req_rep_base(self, typ, **kwargs):
        req = {"typ": typ}
        req.update(kwargs)
        with self.rlock:
            self.rsock.send(cbor_dump_numpy(req))
            return cbor_load_numpy(self.rsock.recv())

    def req_rep(self, typ, **kwargs):
        return zsv_rep_chk(self.req_rep_base(typ, **kwargs))

    def do_cmd(self, cmd, go = None):
        if go is None:
            go = bool(re.match(r"%%?go\b", cmd))
        if not go:
            return self.req_rep("cmd", cmd = cmd)
        assert self.znc
        uid = uuid.uuid4()
        status = ZStatus(self, uid)
        self.req_rep("cmd", cmd = cmd, go = str(uid))
        return status


import json
import ldap
import re
from getpass import getpass
from urllib.parse import quote
from urllib.request import urlopen
from .zserver import ZError, raise_syntax, unary_op

class MambaAuth(object):
    def __init__(self, config, mdg):
        self.authserver = config["authserver"]
        self.proposalserver = config["proposalserver"]
        self.mdg = mdg
        self.user = None
        self.pw = None
        self.conn = None

    def login(self, user = None):
        user = input("Username: ") if user == None else user
        pw = getpass() if self.pw == None else self.pw
        self.pw = None
        if self.conn:
            raise ZError("dup", "already logged in")
        if not re.match("[A-Za-z0-9_@.]+$", user):
            raise ZError("syntax", "invalid username")
        base = "ou=users,dc=ihep,dc=ac,dc=cn"
        conn = ldap.initialize(self.authserver)
        conn.simple_bind_s("cn=authuser,%s" % base, "authpw")  # XXX
        ret = conn.search_s(base, ldap.SCOPE_SUBTREE, "(cn=%s)" % user, None)
        try:
            conn.simple_bind_s(ret[0][0], pw)
        except:
            raise ZError("deny", "login denied")
        self.conn, self.user = conn, user
        try:
            self.refresh_md()
        except:
            self.logout()
            raise

    def refresh_md(self):
        resp = json.loads(urlopen(
            "%s/api/getByEmail?email=%s" %
            (self.proposalserver, quote(self.user)),
        ).read().decode("UTF-8"))
        if resp["msg"] != "success":
            raise ZError("api/%s" % resp["errorCode"],
                "metadata refresh returned `%s'" % resp["msg"])
        data = resp["body"]["data"]
        if not data:
            raise ZError("empty", "empty beamtime list")
        self.mdg.private["beamtimes"] = data

    def logout(self):
        if not self.conn:
            raise ZError("dup", "already logged out")
        self.conn.unbind()
        self.conn, self.user = None, None
        self.mdg.reset()

class MambaMdGen(object):
    def __init__(self, scan_fmt = None):
        self.scan_fmt = scan_fmt if scan_fmt else (lambda i: "scan%05d" % i)
        self.reset()

    def reset(self):
        self.mds = [{}, {"instruments": {}}]
        self.private = \
            {"scan": -1, "beamtimes": None, "instruments": {}, "mdTrig": []}
        self.advance()

    def advance(self):
        self.private["scan"] += 1
        self.mds[-1]["scanId"] = self.scan_fmt(self.private["scan"])

    def refresh(self, beamtimeId = None):
        if not beamtimeId:
            print([d["beamtimeId"] for d in self.private["beamtimes"]])
            beamtimeId = input("Beamtime ID: ")
        data, = [d for d in self.private["beamtimes"]
            if d["beamtimeId"] == beamtimeId]
        data = data.copy()
        data.update(data.pop("proposal"))
        self.mds[-1].update({k: data.pop(k) for k in ["proposalcode",
            "proposalname", "beamtimeId", "startDate", "endDate"]})
        self.private.update(data)

    def read(self):
        status = [v.trigger() for v in self.private["mdTrig"]]
        [st.wait() for st in status]
        for k, v in self.private["instruments"].items():
            self.mds[-1]["instruments"][k] = v.get()
        ret = {}
        for d in self.mds:
            ret.update(d)
        return ret

    def read_advance(self):
        ret = self.read()
        self.advance()
        return ret

    def read_private(self):
        ret = self.private.copy()
        ret["instruments"] = \
            {k: v.vname(True) for k, v in ret["instruments"].items()}
        ret["mdTrig"] = [v.vname(True) for v in ret["mdTrig"]]
        return ret

    def set(self, delta):
        for k, v in delta.items():
            if v == None:
                if k in self.mds[0]:
                    self.mds[0].pop(k)
                continue
            if k == "sampleName":
                assert re.match("[A-Za-z0-9_]+$", delta["sampleName"])
            self.mds[0][k] = v

def mzs_auth(self, req):
    op, state = unary_op(req), self.get_state(req)
    if op == "pw":
        try:
            state.pw = req["pw"]
            return {"err": ""}
        except:
            raise_syntax(req)
    raise_syntax(req)

def mzs_mdg(self, req):
    op, state = unary_op(req), self.get_state(req)
    if "beamtimeId" not in state.mds[-1]:
        raise ZError("deny", "beamtime ID not selected")
    if op == "read":
        return {"err": "", "ret": state.read()}
    elif op == "read_private":
        return {"err": "", "ret": state.read_private()}
    raise_syntax(req)

addonMzs = {"auth": mzs_auth, "mdg": mzs_mdg}

def state_build(U, config):
    U.mdg = MambaMdGen()
    U.auth = MambaAuth(config["auth_mdg"], U.mdg)

saddon_authmdg = lambda arg: {"mzs": addonMzs, "state": state_build}


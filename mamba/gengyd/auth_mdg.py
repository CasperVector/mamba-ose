import json
import ldap
import re
from urllib.parse import quote
from urllib.request import urlopen
from mamba.backend.auth_mdg import MambaAuthMdg, AuthMdgZsHandler
from mamba.backend.zserver import ZError

class GydAuthMdg(MambaAuthMdg):
    def __init__(self, U, config, scan_fmt = None):
        super().__init__(U, config)
        self.authserver = config.authserver
        self.proposalserver = config.proposalserver
        self.scan_fmt = scan_fmt if scan_fmt else (lambda i: "scan%05d" % i)
        self.user = self.conn = None
        self.reset()

    def reset(self):
        self.mds = [{}, {"instruments": {}}]
        self.priv = \
            {"scan": -1, "beamtimes": None, "instruments": {}, "mdTrig": []}
        self.advance()

    def advance(self):
        self.priv["scan"] += 1
        self.mds[-1]["scanId"] = self.scan_fmt(self.priv["scan"])

    def login(self, user = None):
        user = super().login(user)
        pw, self.pw = self.pw, None
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
            self.get_beamtimes()
        except:
            self.logout()
            raise

    def logout(self):
        if not self.conn:
            raise ZError("dup", "already logged out")
        self.conn.unbind()
        self.conn = self.user = None
        self.reset()

    def get_beamtimes(self):
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
        self.priv["beamtimes"] = data

    def set_beamtime(self, bid = None):
        if not bid:
            print([d["beamtimeId"] for d in self.priv["beamtimes"]])
            bid = input("Beamtime ID: ")
        data, = [d for d in self.priv["beamtimes"] if d["beamtimeId"] == bid]
        data = data.copy()
        data.update(data.pop("proposal"))
        self.mds[-1].update({k: data.pop(k) for k in ["proposalcode",
            "proposalname", "beamtimeId", "startDate", "endDate"]})
        self.priv.update(data)

    def update(self, delta):
        if "sampleName" in delta:
            assert re.match("[A-Za-z0-9_]+$", delta["sampleName"])
        for k, v in delta.items():
            if v is None:
                if k in self.mds[0]:
                    self.mds[0].pop(k)
                continue
            self.mds[0][k] = v

    def read(self):
        status = [v.trigger() for v in self.priv["mdTrig"]]
        [st.wait() for st in status]
        for k, v in self.priv["instruments"].items():
            self.mds[-1]["instruments"][k] = v.get()
        ret = {}
        for d in self.mds:
            ret.update(d)
        return ret

    def read_private(self):
        ret = self.priv.copy()
        ret["instruments"] = \
            {k: v.vname(True) for k, v in ret["instruments"].items()}
        ret["mdTrig"] = [v.vname(True) for v in ret["mdTrig"]]
        return ret

    def md_gen(self, plan, *arg, **kwargs):
        ret = self.read()
        self.advance()
        return ret

def sextend_gydauthmdg(U, config):
    U.mzs.extend(AuthMdgZsHandler())
    U.auth_mdg = GydAuthMdg(U, config)


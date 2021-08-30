import json
import ldap
import re
from getpass import getpass
from urllib.parse import quote
from urllib.request import urlopen
from .zserver import ZError

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
        self.mds = [{}, {}]
        self.private = {"scan": -1, "beamtimes": None}
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
        data.update(data.pop("proposal"))
        self.mds[-1].update({k: data.pop(k) for k in ["proposalcode",
            "proposalname", "beamtimeId", "startDate", "endDate"]})
        self.private.update(data)

    def read(self):
        ret = {}
        for d in self.mds:
            ret.update(d)
        return ret

    def read_advance(self):
        ret = self.read()
        self.advance()
        return ret

    def read_private(self):
        return self.private

    def set(self, delta):
        for k, v in delta.items():
            if v == None:
                if k in self.mds[0]:
                    self.mds[0].pop(k)
                continue
            if k == "sampleName":
                assert re.match("[A-Za-z0-9_]+$", delta["sampleName"])
            self.mds[0][k] = v


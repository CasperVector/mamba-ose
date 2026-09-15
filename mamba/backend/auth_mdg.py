from getpass import getpass
from .zserver import ZChildHandler, raise_syntax, unary_op

class MambaAuthMdg(object):
    def __init__(self, U, config):
        self.U, self.pw = U, None

    def login(self, user = None):
        user = input("Username: ") if user == None else user
        if self.pw is None:
            self.pw = getpass()
        return user

    def logout(self):
        pass

    def read(self):
        return {}

    def read_private(self):
        return {}

    def md_gen(self, plan, *arg, **kwargs):
        return {}

class AuthMdgZsHandler(ZChildHandler):
    handles = ["auth_mdg"]

    def do_auth_mdg(self, req):
        op, state = unary_op(req), self.parent.get_state(req)
        if op == "read":
            return {"err": "", "ret": state.read()}
        elif op == "read_private":
            return {"err": "", "ret": state.read_private()}
        elif op == "pw":
            try:
                state.pw = req["pw"]
                return {"err": ""}
            except:
                raise_syntax(req)
        raise_syntax(req)

def sextend_authmdg(U, config):
    U.mzs.extend(AuthMdgZsHandler())
    U.auth_mdg = MambaAuthMdg(U, config)


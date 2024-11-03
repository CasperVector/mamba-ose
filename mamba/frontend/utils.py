from PyQt5 import QtWidgets
from butils.gutils import MambaModel
from ..backend.zserver import ZError, zsv_rep_chk, zsv_err_fmt

class MambaZModel(MambaModel):
    zcb_mk = lambda self, typ: lambda msg: self.submit(typ, msg)
    mrc_req = lambda self, *args, **kwargs: \
        self.rep_chk(self.mrc.req_rep_base(*args, **kwargs))
    mrc_cmd = lambda self, cmd: self.mrc_req("cmd", cmd = cmd)
    mrc_go = lambda self, end, cmd: \
        self.mrc.do_cmd(cmd).subscribe(self.zcb_mk(end))

    def do_err(self, title, desc):
        QtWidgets.QMessageBox.warning(self.view, title, desc)

    def rep_chk(self, rep):
        try:
            return zsv_rep_chk(rep)
        except ZError as e:
            self.do_err("ZError", zsv_err_fmt(e))
            raise


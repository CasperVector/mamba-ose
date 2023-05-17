from PyQt5 import QtCore, QtWidgets
from ..backend.zserver import ZError, zsv_rep_chk, zsv_err_fmt

def slot_gen(obj, typs0, typs1):
    handles = {typs0.get(typ, typ): getattr(obj, "on_" + typ) for typ in typs1}
    def slot(args):
        hdl = handles.get(args[0])
        hdl and hdl(*args[1:])
    return slot

class MambaModel(QtCore.QObject):
    sigSubmit, sigNotify = QtCore.pyqtSignal(tuple), QtCore.pyqtSignal(tuple)
    submit = lambda self, *args: self.sigSubmit.emit(args)
    notify = lambda self, *args: self.sigNotify.emit(args)
    def sbind(self, styps):
        self.sigSubmit.connect(slot_gen(self, {}, styps))

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

class MambaView(object):
    def sbind(self, model, mtyps, styps):
        self.model = model
        self.styps = {typ: mtyps[0].get(typ, typ) for typ in styps}

    def nbind(self, mtyps, ntyps):
        self.model.sigNotify.connect(slot_gen(self, mtyps[1], ntyps))

    def submit(self, typ, *args):
        self.model.submit(self.styps[typ], *args)


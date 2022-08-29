import sys
import pyqtgraph as pg
from mamba.backend.zserver import zsv_rep_chk
from mamba.backend.mzserver import config_read, client_build
from mamba.frontend.utils import slot_gen, model_connect
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QDoubleValidator
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QApplication, \
    QMainWindow, QWidget, QLabel, QLineEdit, QPushButton

class ImageOrigin(QWidget):
    def __init__(self, model, parent = None, typs = None):
        super().__init__(parent)
        self.first = True
        self.iv = pg.ImageView()
        self.vl = pg.InfiniteLine(angle = 90, movable = False)
        self.hl = pg.InfiniteLine(angle = 0, movable = False)
        self.iv.addItem(self.vl)
        self.iv.addItem(self.hl)
        layout = QHBoxLayout()
        layout.addWidget(self.iv)
        self.setLayout(layout)
        model_connect(self, model, typs, ["img", "origin"])

    def on_img(self, img):
        self.iv.setImage(img, autoLevels = self.first)
        self.first = False

    def on_origin(self, origin):
        self.vl.setValue(origin[0])
        self.hl.setValue(origin[1])

class XesView(QMainWindow):
    def __init__(self, model, parent = None):
        super().__init__(parent)
        self.setWindowTitle("Attitude tuning for XES spectrometer")
        layout0, layout1 = QVBoxLayout(), QHBoxLayout()
        layout1.addWidget(QLabel("Motors:", parent))
        self.mx, self.my = QLineEdit(parent), QLineEdit(parent)
        for widget in [self.mx, self.my]:
            widget.setMinimumWidth(6 * 8)
            widget.setValidator(QDoubleValidator(parent))
            layout1.addWidget(widget, stretch = 1)
        self.update = QPushButton("Update", parent)
        layout1.addWidget(self.update)
        layout1.addWidget(QLabel("Evaluation:", parent))
        self.ev = QLineEdit(parent)
        self.ev.setMinimumWidth(24 * 8)
        layout1.addWidget(self.ev, stretch = 3)
        self.tune = QPushButton("Auto tune", parent)
        layout1.addWidget(self.tune)
        layout0.addLayout(layout1)
        widget = ImageOrigin(model)
        widget.setMinimumHeight(512)
        layout0.addWidget(widget)
        widget = QWidget(self)
        widget.setLayout(layout0)
        self.setCentralWidget(widget)
        self.ev.setEnabled(False)
        self.update.clicked.connect(self.emit_update)
        self.tune.clicked.connect(lambda: self.model.emit("begin_tune"))
        model_connect(self, model, None, ["mode", "motors", "eval"])

    def on_mode(self, mode):
        self.update.setEnabled(mode != "tuning")
        for widget in [self.mx, self.my, self.tune]:
            widget.setEnabled(mode == "staged")

    def on_motors(self, mxy):
        self.mx.setText("%.7g" % mxy[0])
        self.my.setText("%.7g" % mxy[1])

    def on_eval(self, ev):
        self.ev.setText(", ".join("%.7g" % x for x in ev))

    def emit_update(self):
        self.model.emit("update",
            float(self.mx.text()) if self.mx.hasAcceptableInput() else None,
            float(self.my.text()) if self.my.hasAcceptableInput() else None)

class XesModel(QObject):
    sigEmit, sigNote = pyqtSignal(tuple), pyqtSignal(tuple)
    emit = lambda self, *args: self.sigEmit.emit(args)
    note = lambda self, *args: self.sigNote.emit(args)

    def __init__(self, name):
        super().__init__()
        pg.setConfigOptions(imageAxisOrder = "row-major")
        self.name, (self.mrc, self.mnc) = name, client_build(config_read())
        self.app, self.view = QApplication([]), XesView(self)
        self.ad = self.motors = None
        self.app.aboutToQuit.connect(lambda: self.emit("quit"))
        self.sigEmit.connect(slot_gen(self, None,
            ["doc", "quit", "update", "begin_tune", "end_tune"]))
        self.mnc.subscribe("doc", self.zcb_mk("doc"))
        self.do_mode("unstaged")

    def run(self):
        self.mnc.start()
        self.view.show()
        return self.app.exec_()

    def zcb_mk(self, typ):
        return lambda msg: self.emit(typ, msg)

    def do_mode(self, mode):
        self.mode = mode
        self.note("mode", mode)

    def on_doc(self, msg):
        if msg["typ"][1] != "event" or self.mode == "unstaged":
            return
        data = msg["doc"]["data"]
        try:
            self.note("img", data[self.ad])
            self.note("motors", [data[m] for m in self.motors])
            self.note("origin", data["origin"])
            self.note("eval", data["eval"])
        except KeyError:
            return

    def do_stage(self):
        self.mrc.do_cmd("U.%s.stage()\n" % self.name)
        ret = self.mrc.req_rep("%s/names" % self.name)["ret"]
        self.ad, self.motors = ret[0], ret[1:]
        self.do_mode("staged")

    def on_quit(self):
        if self.mode != "unstaged":
            self.mrc.do_cmd("U.%s.unstage()\n" % self.name)

    def on_update(self, mx, my):
        if self.mode == "staged":
            self.mrc.do_cmd("U.%s.move([%f, %f])\n" % (self.name, mx, my))
        elif self.mode == "unstaged":
            self.do_stage()
        else:
            return
        self.mrc.do_cmd("U.%s.refresh()\n" % self.name)

    def on_begin_tune(self):
        self.do_mode("tuning")
        self.mrc.do_cmd("%%go U.%s.auto_tune()\n" % self.name).\
            subscribe(self.zcb_mk("end_tune"))

    def on_end_tune(self, rep):
        self.do_mode("staged")
        zsv_rep_chk(rep)

def main(arg = ""):
    name = arg or "atti_xes"
    sys.exit(XesModel(name).run())

if __name__ == "__main__":
    main()


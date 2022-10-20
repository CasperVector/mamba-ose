import pyqtgraph
import sys
from PyQt5 import QtCore, QtGui, QtWidgets
from mamba.backend.mzserver import config_read, client_build
from mamba.frontend.utils import MambaZModel, MambaView
from mamba.frontend.pgitems import MyImageItem, MyROI, TargetPlot, MyImageView

class XesImage(MambaView, pyqtgraph.GraphicsView):
    def __init__(self, model, parent = None, mtyps = ({}, {})):
        super().__init__(parent)
        ci = MyImageView(view = TargetPlot())
        self.target = ci.view.target
        self.target.setZValue(20)
        ci.view.vl.setZValue(10)
        ci.view.hl.setZValue(10)
        self.roi = MyROI((0, 0))
        self.roi.setZValue(10)
        ci.view.addItem(self.roi)
        self.setCentralItem(ci)
        self.on_img = ci.setImage
        self.on_roi = self.roi.setXywh
        self.on_origin = self.target.setPos
        self.roi.sigRegionChangeFinished.connect\
            (lambda: self.submit("roi", self.roi.getXywh()))
        self.target.sigPositionChangeFinished.connect\
            (lambda: self.submit("origin", tuple(self.target.pos())))
        self.sbind(model, mtyps, ["roi", "origin"])
        self.nbind(mtyps, ["mode", "img", "roi", "origin"])

    def on_mode(self, mode):
        self.roi.setVisible(mode != "unstaged")
        self.target.setVisible(mode != "unstaged")

class XesView(MambaView, QtWidgets.QMainWindow):
    def __init__(self, model, parent = None):
        super().__init__(parent)
        self.setWindowTitle("Attitude tuning for XES spectrometer")
        layout0, layout1 = QtWidgets.QVBoxLayout(), QtWidgets.QHBoxLayout()
        layout1.addWidget(QtWidgets.QLabel("Motors:", parent))
        self.mx = QtWidgets.QLineEdit(parent)
        self.my = QtWidgets.QLineEdit(parent)
        for widget in [self.mx, self.my]:
            widget.setMinimumWidth(6 * 8)
            widget.setValidator(QtGui.QDoubleValidator(parent))
            layout1.addWidget(widget, stretch = 1)
        self.update = QtWidgets.QPushButton("Update", parent)
        layout1.addWidget(self.update)
        layout1.addWidget(QtWidgets.QLabel("Evaluation:", parent))
        self.ev = QtWidgets.QLineEdit(parent)
        self.ev.setMinimumWidth(24 * 8)
        layout1.addWidget(self.ev, stretch = 3)
        self.tune = QtWidgets.QPushButton("Auto tune", parent)
        layout1.addWidget(self.tune)
        layout0.addLayout(layout1)
        widget = XesImage(model)
        widget.setMinimumHeight(512)
        layout0.addWidget(widget)
        widget = QtWidgets.QWidget(self)
        widget.setLayout(layout0)
        self.setCentralWidget(widget)
        self.ev.setEnabled(False)
        self.sbind(model, ({}, {}), ["update", "begin_tune"])
        self.update.clicked.connect(self.submit_update)
        self.tune.clicked.connect(lambda: self.submit("begin_tune"))
        self.nbind(({}, {}), ["mode", "motors", "eval"])

    def on_mode(self, mode):
        self.update.setEnabled(mode != "tuning")
        for widget in [self.mx, self.my, self.tune]:
            widget.setEnabled(mode == "staged")

    def on_motors(self, mxy):
        self.mx.setText("%.7g" % mxy[0])
        self.my.setText("%.7g" % mxy[1])

    def on_eval(self, ev):
        self.ev.setText(", ".join("%.7g" % x for x in ev))

    def submit_update(self):
        self.submit("update",
            float(self.mx.text()) if self.mx.hasAcceptableInput() else None,
            float(self.my.text()) if self.my.hasAcceptableInput() else None)

class XesModel(MambaZModel, QtCore.QObject):
    def __init__(self, name):
        super().__init__()
        self.name, (self.mrc, self.mnc) = name, client_build(config_read())
        self.app, self.view = QtWidgets.QApplication([]), XesView(self)
        self.ad = self.motors = None
        self.app.aboutToQuit.connect(lambda: self.submit("exit"))
        self.mnc.subscribe("doc", self.zcb_mk("doc"))
        self.sbind(["doc", "exit", "update",
            "roi", "origin", "begin_tune", "end_tune"])
        self.do_mode("unstaged")

    def run(self):
        self.mnc.start()
        self.view.show()
        return self.app.exec_()

    def do_mode(self, mode):
        self.mode = mode
        self.notify("mode", mode)

    def on_doc(self, msg):
        if msg["typ"][1] != "event" or self.mode == "unstaged":
            return
        data = msg["doc"]["data"]
        try:
            self.notify("img", data[self.ad])
            self.notify("motors", [data[m] for m in self.motors])
            self.notify("eval", data["eval"])
        except KeyError:
            return

    def do_stage(self):
        self.mrc_cmd("U.%s.stage()\n" % self.name)
        ret = self.mrc_req("%s/names" % self.name)["ret"]
        self.ad, self.motors = ret[0], ret[1:]
        self.do_mode("staged")

    def on_exit(self):
        if self.mode != "unstaged":
            self.mrc_cmd("U.%s.unstage()\n" % self.name)

    def on_update(self, mx, my):
        if self.mode == "staged":
            self.mrc_cmd("U.%s.move([%f, %f])\n" % (self.name, mx, my))
            self.mrc_cmd("U.%s.refresh()\n" % self.name)
        elif self.mode == "unstaged":
            self.do_stage()
            self.mrc_cmd("U.%s.refresh(origin = True)\n" % self.name)
        else:
            return
        xywh, origin = self.mrc_req("%s/roi_origin" % self.name)["ret"]
        self.notify("roi", xywh)
        self.notify("origin", origin)

    def on_roi(self, xywh):
        if self.mode == "tuning":
            self.notify("roi", self.mrc_req\
                ("%s/roi_origin" % self.name)["ret"][0])
            return
        self.notify("roi", self.mrc_cmd\
            ("U.%s.set_roi(%r)\n" % (self.name, xywh))["ret"])
        self.mrc_cmd("U.%s.refresh(acquire = False)\n" % self.name)

    def on_origin(self, origin):
        if self.mode == "tuning":
            self.notify("origin", self.mrc_req\
                ("%s/roi_origin" % self.name)["ret"][1])
            return
        self.notify("origin", self.mrc_cmd\
            ("U.%s.set_origin(%r)\n" % (self.name, origin))["ret"])
        self.mrc_cmd("U.%s.refresh(acquire = False)\n" % self.name)

    def on_begin_tune(self):
        self.do_mode("tuning")
        self.mrc_go("end_tune", "%%go U.%s.auto_tune()\n" % self.name)

    def on_end_tune(self, rep):
        self.do_mode("staged")
        self.rep_chk(rep)

def main(arg = ""):
    name = arg or "atti_xes"
    sys.exit(XesModel(name).run())

if __name__ == "__main__":
    main()


import pyqtgraph
import sys
from PyQt5 import QtGui, QtWidgets
from mamba.backend.mzserver import config_read, client_build
from mamba.frontend.utils import MambaZModel, MambaView
from mamba.frontend.pgitems import \
    MyImageItem, MyPlotItem, MyROI, TargetPlot, MyImageView
from .common import xywh2roi

class XesImage(MambaView, pyqtgraph.GraphicsView):
    def __init__(self, model, parent = None, mtyps = ({}, {})):
        super().__init__(parent)
        ci = MyImageView(view = TargetPlot())
        ci.lut.setColorMap("CET-L16")
        self.target = ci.view.target
        self.target.setZValue(20)
        ci.view.vl.setZValue(10)
        ci.view.hl.setZValue(10)
        self.roi = MyROI((0, 0))
        self.roi.setZValue(10)
        ci.view.addItem(self.roi)
        self.angular = ci.view.plot()
        self.angular.setPen(pyqtgraph.mkPen(color = (0, 255, 0), width = 2))
        plot = MyPlotItem()
        plot.setFixedHeight(180)
        self.radial = plot.plot()
        ci.addItem(plot, row = 1, col = 0, rowspan = 1, colspan = 2)
        self.setCentralItem(ci)
        self.on_img = ci.setImage
        self.on_roi = self.roi.setXywh
        self.on_origin = self.target.setPos
        self.roi.sigRegionChangeFinished.connect\
            (lambda: self.submit("roi", self.roi.getXywh()))
        self.target.sigPositionChangeFinished.connect\
            (lambda: self.submit("origin", tuple(self.target.pos())))
        self.sbind(model, mtyps, ["roi", "origin"])
        self.nbind(mtyps, ["mode", "img", "hist", "roi", "origin"])

    def on_mode(self, mode):
        self.roi.setVisible(mode != "unstaged")
        self.target.setVisible(mode != "unstaged")

    def on_hist(self, hist):
        self.radial.setData(hist[0], hist[1])
        self.angular.setData(hist[2], hist[3])

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
        self.ev.setMinimumWidth(16 * 8)
        layout1.addWidget(self.ev, stretch = 2)
        self.tune = QtWidgets.QPushButton("Auto tune", parent)
        layout1.addWidget(self.tune)
        layout1.addWidget(QtWidgets.QLabel("Temperature:", parent))
        self.temp = QtWidgets.QLineEdit(parent)
        self.temp.setMinimumWidth(8)
        layout1.addWidget(self.temp, stretch = 1)
        layout0.addLayout(layout1)
        widget = XesImage(model)
        widget.setMinimumWidth(900)
        widget.setMinimumHeight(800)
        layout0.addWidget(widget)
        widget = QtWidgets.QWidget(self)
        widget.setLayout(layout0)
        self.setCentralWidget(widget)
        self.ev.setEnabled(False)
        self.temp.setEnabled(False)
        self.sbind(model, ({}, {}), ["update", "begin_tune"])
        self.update.clicked.connect(self.submit_update)
        self.tune.clicked.connect(lambda: self.submit("begin_tune"))
        self.nbind(({}, {}), ["mode", "motors", "eval"])

    def on_mode(self, mode):
        self.update.setEnabled(mode != "tuning")
        for widget in [self.mx, self.my, self.tune]:
            widget.setEnabled(mode == "staged")

    def on_motors(self, mxy):
        mx, my = mxy
        if mx is not None:
            self.mx.setText("%g" % mx)
        if my is not None:
            self.my.setText("%g" % my)

    def on_eval(self, ev):
        self.ev.setText(", ".join("%g" % x for x in ev[:-1]))
        self.temp.setText("%g" % ev[-1])

    def submit_update(self):
        self.submit("update",
            float(self.mx.text()) if self.mx.hasAcceptableInput() else None,
            float(self.my.text()) if self.my.hasAcceptableInput() else None)

class XesModel(MambaZModel):
    def __init__(self, name):
        super().__init__()
        self.name, (self.mrc, self.mnc) = name, client_build(config_read())
        self.app, self.view = QtWidgets.QApplication([]), XesView(self)
        self.ad = self.motors = None
        self.mnc.subscribe("doc", self.zcb_mk("doc"))
        self.mnc.subscribe("monitor", self.zcb_mk("monitor"))
        self.sbind(["monitor", "doc", "update",
            "roi", "origin", "begin_tune", "end_tune"])
        self.do_mode("unstaged")

    def run(self):
        self.mnc.start()
        self.view.show()
        return self.app.exec_()

    def do_mode(self, mode):
        self.mode = mode
        self.notify("mode", mode)

    def on_monitor(self, msg):
        if self.mode == "unstaged":
            return
        if msg["typ"][1] == "position":
            self.notify("motors",
                [msg["doc"]["data"].get(m) for m in self.motors])
        elif msg["typ"][1] == "image":
            img = msg["doc"]["data"].get(self.ad)
            if img is not None:
                self.notify("img", img)

    def on_doc(self, msg):
        if msg["typ"][1] != "event" or self.mode == "unstaged":
            return
        data = msg["doc"]["data"]
        try:
            self.notify("img", data[self.ad])
            self.notify("motors", [data[m] for m in self.motors])
            self.notify("eval", data["aeval"])
            self.notify("hist", data["hist"])
        except KeyError:
            return

    def do_stage(self):
        (self.ad,), self.motors = self.mrc_req("%s/names" % self.name)["ret"]
        self.do_mode("staged")

    def on_update(self, mx, my):
        if self.mode == "staged":
            if None not in [mx, my]:
                self.mrc_cmd("U.%s.put_x([%s, %s])\n" % (self.name, mx, my))
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
        if self.mode != "tuning":
            self.mrc_cmd("U.%s.set_roi(%r)\n" % (self.name, xywh2roi(xywh)))
        self.notify("roi", self.mrc_req\
            ("%s/roi_origin" % self.name)["ret"][0])
        if self.mode != "tuning":
            self.mrc_cmd("U.%s.refresh(acquire = False)\n" % self.name)

    def on_origin(self, origin):
        if self.mode != "tuning":
            self.mrc_cmd("U.%s.set_origin(%r)\n" % (self.name, origin))
        self.notify("origin", self.mrc_req\
            ("%s/roi_origin" % self.name)["ret"][1])
        if self.mode != "tuning":
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


import pyqtgraph
import sys
import time
from PyQt5 import QtCore, QtGui, QtWidgets
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
        for widget in [self.roi, self.target]:
            widget.setVisible(mode != "unstaged")
            widget.setEnabled(mode == "staged")

    def on_hist(self, hist):
        self.radial.setData(hist[0], hist[1])
        if hist[2] is not None and hist[3] is not None:
            self.angular.setData(hist[2], hist[3])

class XesView(MambaView, QtWidgets.QMainWindow):
    def __init__(self, model, parent = None):
        super().__init__(parent)
        self.setWindowTitle("XES experiment")
        layout0, layout1 = QtWidgets.QVBoxLayout(), QtWidgets.QHBoxLayout()
        layout1.addWidget(QtWidgets.QLabel("Acquire time:", self))
        self.atime = QtWidgets.QLineEdit(self)
        self.atime.setMinimumWidth(8 * 8)
        self.atime.setValidator(QtGui.QDoubleValidator(self))
        layout1.addWidget(self.atime, stretch = 1)
        layout1.addWidget(QtWidgets.QLabel("Save path:", self))
        self.output = QtWidgets.QLineEdit(self)
        self.output.setMinimumWidth(40 * 8)
        layout1.addWidget(self.output, stretch = 4)
        layout0.addLayout(layout1)
        layout1 = QtWidgets.QHBoxLayout()
        self.acquire = QtWidgets.QPushButton("Acquire image", self)
        layout1.addWidget(self.acquire)
        self.reorigin = QtWidgets.QPushButton("Auto origin", self)
        layout1.addWidget(self.reorigin)
        layout1.addWidget(QtWidgets.QLabel("Evaluation:", self))
        self.ev = QtWidgets.QLineEdit(self)
        self.ev.setMinimumWidth(16 * 8)
        layout1.addWidget(self.ev, stretch = 2)
        layout1.addWidget(QtWidgets.QLabel("Temperature:", self))
        self.temp = QtWidgets.QLineEdit(self)
        self.temp.setMinimumWidth(4 * 8)
        layout1.addWidget(self.temp, stretch = 1)
        layout0.addLayout(layout1)
        widget = XesImage(model)
        widget.setMinimumHeight(600)
        layout0.addWidget(widget)
        widget = QtWidgets.QWidget(self)
        widget.setLayout(layout0)
        self.setCentralWidget(widget)
        self.ev.setReadOnly(True)
        self.temp.setReadOnly(True)
        self.sbind(model, ({}, {}), ["acquire_time",
            "begin_refresh", "stop_refresh", "stop_reorigin"])
        self.atime.returnPressed.connect(lambda:
            self.submit("acquire_time", float(self.atime.text())))
        self.acquire.clicked.connect(lambda: self.submit_acquire(True))
        self.reorigin.clicked.connect(lambda: self.submit_acquire(False))
        self.nbind(({}, {}), ["mode", "acquire_time", "eval"])

    def on_mode(self, mode):
        for widget in [self.atime, self.output]:
            widget.setEnabled(mode == "staged")
        self.acquire.setEnabled(mode != "reorigin")
        self.reorigin.setEnabled(mode in ["staged", "reorigin"])
        self.acquire.setText\
            ("Stop exposure" if mode == "acquire" else "Acquire image")
        self.reorigin.setText\
            ("Stop origin" if mode == "reorigin" else "Auto origin")
        self.mode = mode

    def on_acquire_time(self, atime, temp):
        self.atime.setText("%.0f" % atime)
        if temp is not None:
            self.temp.setText("%g" % temp)

    def on_eval(self, ev):
        self.ev.setText(", ".join("%g" % x for x in ev))

    def submit_acquire(self, acquire):
        if self.mode == "acquire":
            self.submit("stop_refresh")
        elif self.mode == "reorigin":
            self.submit("stop_reorigin")
        else:
            self.submit("begin_refresh",
                self.output.text() if acquire else None)

class XesModel(MambaZModel):
    def __init__(self, name):
        super().__init__()
        self.name, (self.mrc, self.mnc) = name, client_build(config_read())
        self.app, self.view = QtWidgets.QApplication([]), XesView(self)
        self.mode = self.aratio = None
        self.ad = self.img_name = self.atime = self.stamp = None
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(False)
        self.timer.timeout.connect(lambda: self.submit("timer"))
        self.mnc.subscribe("doc", self.zcb_mk("doc"))
        self.mnc.subscribe("monitor", self.zcb_mk("monitor"))
        self.sbind(["monitor", "doc", "roi", "origin", "acquire_time", "timer",
            "stop_refresh", "stop_reorigin", "begin_refresh", "end_refresh"])
        self.do_mode("unstaged")

    def run(self):
        self.mnc.start()
        self.view.show()
        return self.app.exec_()

    def do_mode(self, mode):
        if mode == "acquire":
            atime, temp = [
                self.mrc_req("dev/read", path = "%s.cam.%s" % (self.ad, attr))\
                    ["ret"]["%s.cam.%s" % (self.ad, attr)]["value"]
                for attr in ["acquire_time", "temperature_actual"]
            ]
            self.atime = atime / self.aratio
            self.stamp = time.monotonic() + self.atime
            self.notify("acquire_time", self.atime, temp)
            self.timer.start(500)
        elif self.mode == "acquire":
            self.timer.stop()
            self.notify("acquire_time", self.atime, None)
        self.mode = mode
        self.notify("mode", mode)

    def on_monitor(self, msg):
        if self.mode == "unstaged":
            return
        if msg["typ"][1] == "image":
            img = msg["doc"]["data"].get(self.img_name)
            if img is not None:
                self.notify("img", img)

    def on_doc(self, msg):
        if msg["typ"][1] != "event" or self.mode == "unstaged":
            return
        data = msg["doc"]["data"]
        for k1, k2 in [
            ("img", self.img_name), ("eval", "aeval"),
            ("hist", "hist"), ("origin", "origin")
        ]:
            if k2 in data:
                self.notify(k1, data[k2])

    def on_begin_refresh(self, output):
        if self.mode == "unstaged":
            ret = self.mrc_req("%s/names" % self.name)["ret"]
            self.aratio, (self.ad,) = ret["atime_ratio"], ret["dets"]
            self.img_name = self.ad.replace(".", "_") + "_image"
            self.do_mode("acquire")
            self.mrc_go("end_refresh", "%%go U.%s.refresh()\n" % self.name)
        elif output is not None:
            self.do_mode("acquire")
            self.mrc_go("end_refresh",
                "%%go U.%s.refresh(%r)\n" % (self.name, output))
        else:
            self.do_mode("reorigin")
            self.mrc_go("end_refresh",
                "%%go U.%s.refresh(mode = 'o')\n" % self.name)

    def on_end_refresh(self, rep = None):
        xywh, origin = self.mrc_req("%s/roi_origin" % self.name)["ret"]
        self.notify("roi", xywh)
        self.notify("origin", origin)
        self.do_mode("staged")
        if rep:
            self.rep_chk(rep)

    def on_stop_refresh(self):
        self.mrc_cmd("%s.cam.acquire.set(0).wait()\n" % self.ad)

    def on_stop_reorigin(self):
        self.mrc_cmd("U.%s.stop()\n" % self.name)

    def on_acquire_time(self, atime):
        self.mrc_cmd("%s.cam.acquire_time.set(%d).wait()\n" %
            (self.ad, round(atime * self.aratio)))

    def on_timer(self):
        if self.mode == "acquire":
            self.notify("acquire_time",
                max(self.stamp - time.monotonic(), 0.0), None)

    def on_roi(self, xywh):
        if self.mode == "staged":
            self.mrc_cmd("U.%s.set_roi(%r)\n" % (self.name, xywh2roi(xywh)))
        self.notify("roi", self.mrc_req\
            ("%s/roi_origin" % self.name)["ret"][0])
        if self.mode == "staged":
            self.mrc_cmd("U.%s.refresh(mode = '')\n" % self.name)

    def on_origin(self, origin):
        if self.mode == "staged":
            self.mrc_cmd("U.%s.set_origin(%r)\n" % (self.name, origin))
        self.notify("origin", self.mrc_req\
            ("%s/roi_origin" % self.name)["ret"][1])
        if self.mode == "staged":
            self.mrc_cmd("U.%s.refresh(mode = '')\n" % self.name)

def main(arg = ""):
    name = arg or "atti_xes"
    sys.exit(XesModel(name).run())

if __name__ == "__main__":
    main()


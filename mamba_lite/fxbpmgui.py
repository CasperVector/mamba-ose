#!/usr/bin/python3

import numpy
import pyqtgraph
import sys
import threading
from PIL import Image
from PyQt5 import QtCore, QtWidgets
from butils.gutils import MambaModel, MambaView
from butils.pgitems import AlignedLines, MyROI, ProjectImage
from .fxbpm import FxBpmServer, fmt_pos, fmt_time, roi_crop, xywh2roi

class FxBpmPlot(MambaView, pyqtgraph.GraphicsView):
    def __init__(self, model, titles, parent = None, mtyps = ({}, {})):
        super().__init__(parent)
        self.timer, self.delay = QtCore.QTimer(), 100
        self.timer.setSingleShot(True)
        self.ci = AlignedLines()
        self.ci.doStage(titles)
        self.setCentralItem(self.ci)
        self.timer.timeout.connect(lambda: self.submit("bpm_idle"))
        self.sbind(model, mtyps, ["bpm_idle"])
        self.nbind(mtyps, ["lines"])

    def on_lines(self, lines):
        self.ci.titles[0].setText("Time (s) - %s" % fmt_time(lines[0][-1]))
        lines[0] = lines[0] - lines[0][-1]
        for i, line in enumerate(self.ci.lines):
            line.setData(lines[0], lines[i + 1])
        self.timer.start(self.delay)

class FxBpmImage(MambaView, pyqtgraph.GraphicsView):
    def __init__(self, model, parent = None, mtyps = ({}, {})):
        super().__init__(parent)
        self.timer, self.delay = QtCore.QTimer(), 100
        self.xywh = self.xs = self.ys = self.crop = self.mode = None
        self.timer.setSingleShot(True)
        self.ci = ProjectImage()
        self.ci.lut.gradient.setColorMap(pyqtgraph.colormap.get("CET-L16"))
        self.ci.lut.gradient.showTicks(False)
        self.roi = MyROI((0, 0))
        self.roi.setZValue(10)
        self.ci.view.addItem(self.roi)
        self.setCentralItem(self.ci)
        self.on_roi = self.roi.setXywh
        self.ci.image.hoverEvent = self.submit_hover
        self.timer.timeout.connect(lambda: self.submit("img_idle"))
        self.roi.sigRegionChangeFinished.connect\
            (lambda: self.submit("roi", self.roi.getXywh()))
        self.sbind(model, mtyps, ["roi", "hover", "img_idle"])
        self.nbind(mtyps, ["mode", "crop", "img", "roi"])

    def on_mode(self, mode):
        self.mode = mode
        self.roi.setVisible(mode == "open")

    def on_crop(self, xywh):
        self.ci.setShift(*xywh[:2])
        self.wh, roi = xywh[2:], xywh2roi(xywh)
        self.crop = lambda img: roi_crop(img, roi)

    def on_img(self, img):
        self.ci.setImage(self.crop(img))
        self.timer.start(self.delay)

    def submit_hover(self, ev):
        if ev.isExit():
            return
        i, j = numpy.array(self.ci.shift) + \
            numpy.clip(ev.pos(), 0, self.wh).astype(int)
        self.submit("hover", (i, j))

class FxBpmView(MambaView, QtWidgets.QMainWindow):
    def __init__(self, model, parent = None):
        super().__init__(parent)
        self.setWindowTitle("Fluorescent screen BPM")
        self.bpm, self.hover, self.buttons = [], [], []
        layout1, layout0 = QtWidgets.QGridLayout(), QtWidgets.QVBoxLayout()
        for i, j, desc in [
            (0, 1, "px"), (0, 2, "um"),
            (1, 0, "Centre X"), (2, 0, "Centre Y"),
            (3, 0, "Mouse X"), (4, 0, "Mouse Y"),
            (5, 1, "HM-ROI mean"), (5, 2, "At mouse"),
            (6, 0, "Intensity")
        ]:
            layout1.addWidget(QtWidgets.QLabel(desc), i, j)
        for group, ijs in [
            (self.bpm, [(1, 1), (2, 1), (1, 2), (2, 2), (6, 1)]),
            (self.hover, [(3, 1), (4, 1), (3, 2), (4, 2), (6, 2)])
        ]:
            for i, j in ijs:
                group.append(QtWidgets.QLineEdit(self))
                group[-1].setReadOnly(True)
                layout1.addWidget(group[-1], i, j)
        layout0.addLayout(layout1)
        layout1 = QtWidgets.QGridLayout()
        for i, (desc, slot) in enumerate([
            ("Update", lambda: self.submit("update")),
            ("Auto ROI", lambda: self.submit("roi", None)),
            ("Start", lambda: self.submit(self.buttons[2].text().lower()))
        ]):
            self.buttons.append(QtWidgets.QPushButton(desc, self))
            self.buttons[-1].clicked.connect(slot)
            layout1.addWidget(self.buttons[-1], 0, i)
        self.path = QtWidgets.QLineEdit()
        layout1.addWidget(self.path, 1, 0, 1, 2)
        self.buttons.append(QtWidgets.QPushButton("Save image", self))
        self.buttons[-1].clicked.connect\
            (lambda: self.submit("save", self.path.text()))
        layout1.addWidget(self.buttons[-1], 1, 2)
        layout0.addLayout(layout1)
        layout0.addWidget(FxBpmPlot(model,
            ["Time (s)", "Centre X (um)", "Centre Y (um)"]))
        layout1, layout0 = layout0, QtWidgets.QHBoxLayout()
        widget = QtWidgets.QWidget(self)
        widget.setLayout(layout1)
        widget.setMinimumWidth(360)
        widget.setMaximumWidth(500)
        layout0.addWidget(widget)
        widget = FxBpmImage(model)
        widget.setMinimumWidth(600)
        widget.setMinimumHeight(600)
        layout0.addWidget(widget)
        widget = QtWidgets.QWidget(self)
        widget.setLayout(layout0)
        self.setCentralWidget(widget)
        self.sbind(model, ({}, {}), ["update", "roi", "start", "stop", "save"])
        self.nbind(({}, {}), ["mode", "bpm", "hover"])

    def on_mode(self, mode):
        self.mode = mode
        self.buttons[0].setEnabled(self.mode != "acquiring")
        self.buttons[1].setEnabled(self.mode == "open")
        self.buttons[2].setEnabled(self.mode != "closed")
        self.buttons[3].setEnabled(self.mode != "closed")
        self.buttons[2].setText("Stop" if self.mode == "acquiring" else "Start")

    on_bpm = lambda self, ijxyc: [widget.setText(fmt_pos(val))
        for widget, val in zip(self.bpm, ijxyc)]
    on_hover = lambda self, ijxyc: [widget.setText(fmt_pos(val))
        for widget, val in zip(self.hover, ijxyc)]

class FxBpmModel(MambaModel):
    def __init__(self):
        super().__init__()
        pyqtgraph.setConfigOptions(background = "w", foreground = "k")
        self.app, self.view = QtWidgets.QApplication([]), FxBpmView(self)
        self.server, self.idle = FxBpmServer(self.submit), [False, False]
        self.app.aboutToQuit.connect(lambda: self.submit("exit"))
        self.sbind(["err", "exit", "update", "roi", "start", "stop",
            "img", "img_idle", "bpm", "bpm_idle", "hover", "save"])
        self.do_mode("closed")

    def run(self, *argv):
        self.server.open(*argv)
        self.loop = threading.Thread(target = self.server.serve, daemon = True)
        self.loop.start()
        self.view.showMaximized()
        self.view.show()
        return self.app.exec_()

    def do_mode(self, mode):
        self.mode = mode
        self.notify("mode", mode)

    def on_err(self, typ, desc):
        QtWidgets.QMessageBox.warning(self.view, typ, "%s: %s" % (typ, desc))

    def request(self, *req):
        rep = self.server.request(*req)
        if rep[0]:
            self.on_err(*rep)
            return None
        return rep

    def on_exit(self):
        while True:
            if self.request("exit")[-1] == "close":
                self.loop.join()
                self.server.close()
                return

    def do_trans(self, acquiring):
        if acquiring:
            xywh = self.request("roi")[-1]
        else:
            shape = self.server.shape
            xywh = (0, 0, shape[1], shape[0])
        self.notify("crop", xywh)

    def on_update(self):
        self.request("update")

    def on_roi(self, xywh):
        self.notify("roi", self.request("roi", xywh)[-1])

    def on_start(self):
        if self.request("start"):
            self.do_trans(True)
            self.do_mode("acquiring")
            self.idle = [True, True]

    def on_stop(self):
        if self.request("stop"):
            self.do_trans(False)
            self.do_mode("open")

    def on_img(self, img, time):
        if self.mode != "acquiring" or self.idle[0]:
            self.img = img, time
            if self.mode == "closed":
                self.notify("roi", self.request("roi")[-1])
                self.do_trans(False)
                self.do_mode("open")
            self.notify("img", img)
            self.idle[0] = False

    def on_img_idle(self):
        self.idle[0] = True

    def on_bpm(self, bpm, lines):
        if self.mode != "acquiring" or self.idle[1]:
            self.notify("bpm", bpm)
            self.notify("lines", lines)
            self.idle[1] = False

    def on_bpm_idle(self):
        self.idle[1] = True

    def on_hover(self, ij):
        try:
            c = self.img[0][ij[1], ij[0]]
            self.notify("hover", self.server.ijxy(ij) + (c,))
        except IndexError:
            pass

    def on_save(self, path):
        if path and path[-1] not in "/-":
            path += "-"
        path += fmt_time(self.img[1]) + ".tiff"
        Image.fromarray(self.img[0]).save(path)

def main(argv):
    for i in [1, 3]:
        if len(argv) > i:
            argv[i] = float(argv[i])
    model = FxBpmModel()
    return model.run(*argv)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


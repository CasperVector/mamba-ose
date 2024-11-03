#!/usr/bin/python3

import epics
import pyqtgraph
import sys
from PyQt5 import QtCore, QtWidgets
from butils.gutils import MambaModel, MambaView
from butils.pgitems import MyImageView, gv_wrap

def gen_reshape(shape):
    if any(v is None for v in shape.values()) or not shape["nd"] or \
        not all(shape[x] for x in ["x0", "x1", "x2"][:min(3, shape["nd"])]):
        return None
    if shape["cm"] == 0 and not shape["x2"] and shape["x1"] and shape["x0"]:
        return lambda img: img.reshape((shape["x1"], shape["x0"]))
    if shape["x0"] == 3 and ((shape["cm"] == 2 and shape["x2"] and shape["x1"])
        or (shape["cm"] == 0 and shape["x2"] >= 10 and shape["x1"] >= 10)):
        return lambda img: img.reshape((shape["x2"], shape["x1"], shape["x0"]))
    if shape["x1"] == 3 and ((shape["cm"] == 3 and shape["x2"] and shape["x0"])
        or (shape["cm"] == 0 and shape["x2"] >= 10 and shape["x0"] >= 10)):
        return lambda img: img.reshape((shape["x2"], shape["x1"], shape["x0"]))\
            .transpose((0, 2, 1))
    if shape["x2"] == 3 and ((shape["cm"] == 4 and shape["x1"] and shape["x0"]) \
        or (shape["cm"] == 0 and shape["x1"] >= 10 and shape["x0"] >= 10)):
        return lambda img: img.reshape((shape["x2"], shape["x1"], shape["x0"]))\
            .transpose((1, 2, 0))
    sys.stderr.write("Unexpected shape: cm nd x0 x1 x2 = %d %d %d %d %d\n" %
        tuple(shape[key] for key in "cm nd x0 x1 x2".split()))

class ImgWatchView(MambaView, QtWidgets.QMainWindow):
    def __init__(self, model, prefix, parent = None, mtyps = ({}, {})):
        super().__init__(parent)
        self.setWindowTitle(prefix)
        self.timer, self.delay, self.reshape = QtCore.QTimer(), 100, None
        self.timer.setSingleShot(True)
        self.ci = MyImageView()
        self.setCentralWidget(gv_wrap(self.ci))
        self.timer.timeout.connect(lambda: self.submit("idle"))
        self.sbind(model, mtyps, ["idle"])
        self.nbind(mtyps, ["reshape", "img"])

    def on_reshape(self, reshape):
        self.reshape = reshape

    def on_img(self, img):
        try:
            img = self.reshape(img)
        except ValueError:
            pass
        else:
            self.ci.setImage(img)
        self.timer.start(self.delay)

class ImgWatchModel(MambaModel):
    def __init__(self, prefix):
        super().__init__()
        pyqtgraph.setConfigOptions(background = "w", foreground = "k")
        self.app = QtWidgets.QApplication([])
        self.view = ImgWatchView(self, prefix)
        self.shape, self.reshaper = {}, {}
        self.idle, self.reshape, self.delayed = True, None, None
        reshaper = {"x0": "ArraySize0", "x1": "ArraySize1",
            "x2": "ArraySize2", "nd": "NDimensions", "cm": "ColorMode"}
        for key in reshaper:
            self.shape[key] = None
        for key, suffix in reshaper.items():
            self.reshaper[key] = epics.PV\
                ("%simage1:%s_RBV" % (prefix, suffix), auto_monitor = True)
            self.reshaper[key].add_callback((lambda key:
                lambda *, value, **kwargs: self.submit("reshape", key, value)
            )(key))
        self.img = epics.PV(prefix + "image1:ArrayData", auto_monitor = True)
        self.img.add_callback\
            (lambda *, value, **kwargs: self.submit("img", value))
        self.sbind(["reshape", "img", "idle"])

    def run(self, *argv):
        self.view.show()
        return self.app.exec_()

    def do_delayed(self):
        if self.idle and self.reshape and self.delayed is not None:
            self.notify("img", self.delayed)
            self.delayed, self.idle = None, False

    def on_reshape(self, key, value):
        self.shape[key] = value
        self.reshape = gen_reshape(self.shape)
        self.notify("reshape", self.reshape)
        self.do_delayed()

    def on_img(self, img):
        self.delayed = img
        self.do_delayed()

    def on_idle(self):
        self.idle = True
        self.do_delayed()

if __name__ == "__main__":
    model = ImgWatchModel(*sys.argv[1:])
    sys.exit(model.run())


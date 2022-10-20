import numpy
import pyqtgraph
from PyQt5 import QtGui
from pyqtgraph.graphicsItems.TargetItem import TargetItem

def gv_wrap(item):
    gv = pyqtgraph.GraphicsView()
    gv.setCentralItem(item)
    return gv

class MyImageItem(pyqtgraph.ImageItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setOpts(axisOrder = "row-major")
        self.first = True

    def setImage(self, img = None, autoLevels = None, **kwargs):
        if autoLevels is None:
            autoLevels = self.first
        super().setImage(img, autoLevels = autoLevels, **kwargs)
        if img is not None:
            self.first = False

class MyROI(pyqtgraph.ROI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for a, b in [[(0, 0), (1, 1)], [(0, 1), (1, 0)],
            [(0, 0.5), (1, 0.5)], [(0.5, 0), (0.5, 1)]]:
            self.addScaleHandle(a, b)
            self.addScaleHandle(b, a)

    def getXywh(self):
        return tuple(int(x) for x in tuple(self.pos()) + tuple(self.size()))

    def setXywh(self, xywh):
        self.setPos(*xywh[:2], finish = False)
        self.setSize(xywh[2:], finish = False)

class TargetPlot(pyqtgraph.PlotItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target = TargetItem(symbol = "o")
        self.vl = pyqtgraph.InfiniteLine(angle = 90, movable = False)
        self.hl = pyqtgraph.InfiniteLine(angle = 0, movable = False)
        self.addItem(self.target)
        self.addItem(self.vl)
        self.addItem(self.hl)
        self.target.sigPositionChanged.connect(self.targetChanged)

    def targetChanged(self):
        origin = self.target.pos()
        self.vl.setValue(origin[0])
        self.hl.setValue(origin[1])

class MyImageView(pyqtgraph.GraphicsLayout):
    def __init__(self, *args, view = None, imageItem = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.doStage(view, imageItem)
        self.addItem(self.view, row = 0, col = 0)
        self.addItem(self.lut, row = 0, col = 1)

    def doStage(self, view, imageItem):
        self.view = view or pyqtgraph.PlotItem()
        self.view.setAspectLocked(True)
        self.view.invertY()
        self.image = imageItem or MyImageItem()
        self.image.setOpts(axisOrder = "row-major")
        self.view.addItem(self.image)
        self.lut = pyqtgraph.HistogramLUTItem()
        self.lut.setImageItem(self.image)
        self.setShift(0, 0)

    def setShift(self, x, y):
        self.shift = x, y
        self.image.setTransform(QtGui.QTransform().translate(x, y))

    def setImage(self, image, autoRange = True, **kwargs):
        self.image.setImage(image, **kwargs)
        if autoRange:
            self.view.autoRange()


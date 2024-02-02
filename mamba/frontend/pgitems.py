import numpy
import pyqtgraph
import weakref
from PyQt5 import QtCore, QtGui, QtWidgets
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

class MyPlotItem(pyqtgraph.PlotItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setClipToView(True)
        self.setDownsampling(mode = "peak")

class MultiRois(pyqtgraph.PlotItem):
    def doStage(self, n, z = 10):
        self.rois, self.texts = [], []
        for i in range(n):
            text = pyqtgraph.TextItem(str(i))
            self.addItem(text)
            roi = MyROI((0, 0))
            roi.setZValue(z)
            self.addItem(roi)
            self.rois.append(roi)
            self.texts.append(text)
            roi.sigRegionChanged.connect\
                ((lambda i: lambda: self.roiChanged(i))(i))

    def roiChanged(self, i):
        self.texts[i].setPos(*self.rois[i].pos())

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

class ThumbLines(pyqtgraph.GraphicsLayout):
    def doStage(self, n, cols, transpose = True):
        self.setBorder((127, 127, 127))
        self.lines = []
        if transpose:
            cols = numpy.ceil(n / cols)
        for i in range(n):
            sub = self.addLayout(i % cols, i // cols) \
                if transpose else self.addLayout(i // cols, i % cols)
            sub.addLabel(str(i))
            box = sub.addViewBox()
            line = pyqtgraph.PlotDataItem()
            line.setClipToView(True)
            line.setDownsampling(method = "peak")  # WTF param name?
            box.addItem(line)
            self.lines.append(line)

class AlignedLines(pyqtgraph.GraphicsLayout):
    def doStage(self, titles, pen = "k"):
        self.lines, self.titles = [], []
        self.titles.append(self.addLabel(titles[0], row = len(titles), col = 1))
        for title in titles[1:]:
            self.titles.append(self.addLabel(title,
                row = len(self.lines), col = 0, angle = 270))
            line = self.addPlot(row = len(self.lines), col = 1)
            line.setClipToView(True)
            line.setDownsampling(mode = "peak")
            line.setMouseEnabled(x = True, y = False)
            self.lines.append(line)
        for i, line in enumerate(self.lines):
            for axis, show in [("left", True), ("right", False),
                ("top", False), ("bottom", True)]:
                line.showAxis(axis, show)
            if i:
                line.setXLink(self.lines[0])
        self.lines = [line.plot(pen = pen) for line in self.lines]

class OptimScatter(pyqtgraph.GraphicsLayout):
    def __init__(self, dark = True):
        super().__init__()
        self.dark = dark

    def doStage(self, motors):
        self.plots = []
        self.data = numpy.array([], dtype = "float").\
            reshape((0, len(motors) + 1))
        self.vls = []
        for i, name in enumerate(motors):
            self.addLabel(name, row = i, col = 0)
            plot = self.addPlot(row = i, col = 1)
            plot.showAxis("left", False)
            plot.setMouseEnabled(x = True, y = False)
            self.plots.append(self.makePlot())
            self.vls.append(pyqtgraph.InfiniteLine(angle = 90, movable = False))
            plot.addItem(self.plots[-1])
            plot.addItem(self.vls[-1])

    def makePlot(self):
        return pyqtgraph.PlotDataItem(size = 10,
            pen = (127, 127, 127), symbolPen = pyqtgraph.mkPen(None))

    def scaleData(self, y):
        if len(y):
            y = y - y.min()
            if y.max():
                y = y / y.max()
        return y

    def makeBrush(self, y):
        if not hasattr(self, "cmap"):
            self.cmap = pyqtgraph.colormap.get("CET-L16")
        brush = self.cmap.map(1 - y if self.dark else y)
        brush[:,3] = 170
        return brush

    def setData(self, data):
        assert data.shape[1:] == self.data.shape[1:]
        self.data = data
        y = self.scaleData(data[:,-1])
        brush = self.makeBrush(y)
        for i, (plot, vl) in enumerate(zip(self.plots, self.vls)):
            plot.setData(data[:,i], y, symbolBrush = brush)
            vl.setValue(data[-1, i] if len(data) else 0)

    def addPoints(self, data):
        self.setData(numpy.concatenate((self.data, data)))

class OptimMap(OptimScatter):
    def __init__(self, dark = True):
        super().__init__(dark = dark)
        self.plot = self.makePlot()
        self.vl = pyqtgraph.InfiniteLine(angle = 90, movable = False)
        self.hl = pyqtgraph.InfiniteLine(angle = 0, movable = False)
        pi = self.addPlot()
        pi.addItem(self.plot)
        pi.addItem(self.vl)
        pi.addItem(self.hl)
        self.data = numpy.array([], dtype = "float").reshape((0, 3))

    def setData(self, data):
        assert data.shape[1:] == self.data.shape[1:]
        self.data = data
        self.plot.setData(data[:,0], data[:,1],
            symbolBrush = self.makeBrush(self.scaleData(data[:,-1])))
        cur = data[-1] if len(data) else [0, 0]
        self.vl.setValue(cur[0])
        self.hl.setValue(cur[1])

class HistoColorBarItem(pyqtgraph.GraphicsWidget):
    cmaps = ("CET-L16", "CET-R2")

    def __init__(self, image = None, colorMap = None, position = "right"):
        super().__init__()
        self.image = lambda: None
        self.colorMap = None
        self.menu = QtWidgets.QMenu()
        self.actions = QtWidgets.QActionGroup(self.menu)
        for i, cmap in enumerate(("(Grayscale)",) + self.cmaps):
            action = QtWidgets.QAction(cmap, self.menu)
            action.setCheckable(True)
            action.triggered.connect((lambda cmap:
                lambda: self.setColorMap(cmap))(cmap if i else None))
            self.actions.addAction(action)
        self.menu.addActions(self.actions.actions())
        self.actions.actions()[0].setChecked(True)
        def mouseClickEvent(ev):
            if ev.button() == QtCore.Qt.MouseButton.RightButton:
                ev.accept()
                self.menu.popup(ev.screenPos().toQPoint())

        self.vb = pyqtgraph.ViewBox(parent = self)
        self.vb.enableAutoRange(self.vb.XYAxes)
        if position in ["left", "right"]:
            self.vb.setMaximumWidth(100)
            self.vb.setMinimumWidth(30)
            self.vb.setMouseEnabled(x = False, y = True)
        else:
            self.vb.setMaximumHeight(100)
            self.vb.setMinimumHeight(30)
            self.vb.setMouseEnabled(x = True, y = False)
        ax = {"left": "right", "right": "left",
            "top": "bottom", "bottom": "top"}[position]
        self.axis = pyqtgraph.AxisItem(ax,
            maxTickLength = -10, linkView = self.vb, parent = self)

        regOrient = "horizontal" \
            if position in ["left", "right"] else "vertical"
        self.region = pyqtgraph.LinearRegionItem\
            ([0, 1], regOrient, swapMode = "block")
        self.region.setZValue(1000)
        self.region.lines[0].addMarker("<|>", size = 6)
        self.region.lines[1].addMarker("<|>", size = 6)
        self.region.sigRegionChanged.connect(self.regionChanging)
        self.region.sigRegionChangeFinished.connect(self.regionChanged)
        self.vb.addItem(self.region)
        self.plot = pyqtgraph.PlotCurveItem(pen = (200, 200, 200, 100))
        self.plot.setFillLevel(0.0)
        self.plot.setBrush((100, 100, 200))
        if position in ["left", "right"]:
            self.plot.setRotation(90)
        self.vb.addItem(self.plot)

        self.bar = pyqtgraph.ImageItem(axisOrder = "row-major")
        self.bar.setImage(numpy.linspace(0, 1, 256).reshape
            ((-1, 1) if position in ["left", "right"] else (1, -1)))
        barBox = pyqtgraph.ViewBox(parent = self)
        if position in ["left", "right"]:
            barBox.setFixedWidth(20)
        else:
            barBox.setFixedHeight(20)
        barBox.setMouseEnabled(x = False, y = False)
        barBox.mouseClickEvent = mouseClickEvent
        barBox.addItem(self.bar)

        self.layout = QtWidgets.QGraphicsGridLayout()
        self.layout.setContentsMargins(1, 1, 1, 1)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)
        for w, i in zip([self.axis, self.vb, barBox], [0, 1, 2]
            if position in ["right", "bottom"] else [2, 1, 0]):
            self.layout.addItem(w, *((0, i)
                if position in ["left", "right"] else (i, 0)))
        barBox.setFlag(barBox.GraphicsItemFlag.ItemStacksBehindParent)
        self.vb.setFlag(self.vb.GraphicsItemFlag.ItemStacksBehindParent)
        if image is not None:
            self.setImageItem(image)
        if colorMap is not None:
            self.setColorMap(colorMap)

    def setImageItem(self, img):
        self.image = weakref.ref(img)
        if self.colorMap is not None:
            img.setLookupTable(self.colorMap.getLookupTable(nPts = 256))
        self.regionChanged()
        self.imageChanged(autoLevels = True)
        img.sigImageChanged.connect(self.imageChanged)

    def setColorMap(self, colorMap):
        if isinstance(colorMap, str):
            colorMap = pyqtgraph.colormap.get(colorMap)
        self.colorMap = colorMap
        lut = colorMap and colorMap.getLookupTable(nPts = 256)
        self.bar.setLookupTable(lut)
        img = self.image()
        if img is not None:
            img.setLookupTable(lut)

    def regionChanged(self):
        img = self.image()
        if img is not None:
            img.setLevels(self.region.getRegion())

    def regionChanging(self):
        img = self.image()
        if img is not None:
            img.setLevels(self.region.getRegion())
        self.update()

    def imageChanged(self, autoLevels = False):
        img = self.image()
        if img is None:
            return
        h = img.getHistogram()
        if h[0] is None:
            return
        self.plot.setData(*h)
        mn, mx = (h[0][0], h[0][-1]) if autoLevels else img.levels
        self.region.setRegion([mn, mx])

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
        self.lut = HistoColorBarItem()
        self.lut.setImageItem(self.image)
        self.setShift(0, 0)

    def setShift(self, x, y):
        self.shift = x, y
        self.image.setTransform(QtGui.QTransform().translate(x, y))

    def setImage(self, image, autoRange = True, **kwargs):
        self.image.setImage(image, **kwargs)
        if autoRange:
            self.view.autoRange()

class ProjectImage(MyImageView):
    def __init__(self, *args, view = None,
        imageItem = None, pen = "b", **kwargs):
        pyqtgraph.GraphicsLayout.__init__(self, *args, **kwargs)
        self.doStage(view, imageItem)
        self.addItem(self.view, row = 1, col = 1)
        self.addItem(self.hplot, row = 0, col = 1)
        self.addItem(self.vplot, row = 1, col = 0)
        self.addItem(self.lut, row = 0, col = 2, rowspan = 2, colspan = 1)
        self.vplot.invertX()
        self.vplot.invertY()
        self.hproj.setPen(pen)
        self.vproj.setPen(pen)
        for item, show in [(self.view, ["left", "top"]),
            (self.hplot, ["left"]), (self.vplot, ["top"])]:
            for axis in ["left", "right", "top", "bottom"]:
                item.showAxis(axis, axis in show)

    def doStage(self, *args, **kwargs):
        super().doStage(*args, **kwargs)
        self.hplot = pyqtgraph.PlotItem()
        self.hplot.setXLink(self.view)
        self.hproj = self.hplot.plot()
        self.vplot = pyqtgraph.PlotItem()
        self.vplot.setYLink(self.view)
        self.vproj = self.vplot.plot()
        self.hplot.setMaximumHeight(80)
        self.hplot.setMinimumHeight(24)
        self.vplot.setMaximumWidth(80)
        self.vplot.setMinimumWidth(24)

    def setImage(self, image, **kwargs):
        super().setImage(image, **kwargs)
        xs, ys = numpy.arange(image.shape[1]), numpy.arange(image.shape[0])
        self.hproj.setData(self.shift[0] + xs, image.sum(0))
        self.vproj.setData(image.sum(1), self.shift[1] + ys)


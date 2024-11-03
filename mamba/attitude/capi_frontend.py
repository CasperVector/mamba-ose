import numpy
import pandas
import pyqtgraph
import sys
from PyQt5 import QtCore, QtWidgets
from butils.gutils import MambaView
from butils.pgitems import OptimMap, OptimScatter
from mamba.backend.mzserver import config_read, client_build
from mamba.frontend.utils import MambaZModel

IDLE_PAUSE = 0.2

class CapiScatter(MambaView, pyqtgraph.GraphicsView):
    def __init__(self, model, parent = None, mtyps = ({}, {})):
        super().__init__(parent)
        self.ci = OptimScatter()
        self.setCentralItem(self.ci)
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.sbind(model, mtyps, ["idle"])
        self.nbind(mtyps, ["stage", "data"])
        self.timer.timeout.connect(lambda: self.submit("idle", 0))

    def on_stage(self, motors, outputs, state):
        self.ci.doStage(motors)

    def on_data(self, data):
        self.ci.setData(data)
        self.timer.start(IDLE_PAUSE)

class CapiMap(MambaView, pyqtgraph.GraphicsView):
    def __init__(self, model, parent = None, mtyps = ({}, {})):
        super().__init__(parent)
        self.ci = OptimMap()
        self.setCentralItem(self.ci)
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.sbind(model, mtyps, ["idle"])
        self.nbind(mtyps, ["data2"])
        self.timer.timeout.connect(lambda: self.submit("idle", 1))

    def on_data2(self, data):
        self.ci.setData(data)
        self.timer.start(IDLE_PAUSE)

class CapiScale(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.lo = QtWidgets.QLineEdit("0", self)
        self.lo.setFixedWidth(12 * 8)
        self.lo.setAlignment(QtCore.Qt.AlignRight)
        layout.addWidget(self.lo)
        bar = pyqtgraph.ImageItem(axisOrder = "row-major")
        bar.setImage(numpy.linspace(1.0, 0.1, 256).reshape((1, -1)))
        bar.setLookupTable\
            (pyqtgraph.colormap.get("CET-L16").getLookupTable(nPts = 256))
        vb = pyqtgraph.ViewBox()
        vb.addItem(bar)
        vb.setMouseEnabled(x = False, y = False)
        vb.setMenuEnabled(False)
        gv = pyqtgraph.GraphicsView(background = None)
        gv.setCentralItem(vb)
        gv.setFixedWidth(16 * 8)
        gv.setFixedHeight(32)
        layout.addWidget(gv)
        self.hi = QtWidgets.QLineEdit("0", self)
        self.hi.setFixedWidth(12 * 8)
        layout.addWidget(self.hi)
        self.setLayout(layout)
        self.lo.setReadOnly(True)
        self.hi.setReadOnly(True)

class CapiView(MambaView, QtWidgets.QMainWindow):
    def __init__(self, model, parent = None):
        super().__init__(parent)
        self.setWindowTitle("General attitude tuning")
        layout0 = QtWidgets.QVBoxLayout()
        layout1 = QtWidgets.QHBoxLayout()
        self.pause = QtWidgets.QCheckBox("Pause plot", self)
        layout1.addWidget(self.pause)
        self.autosel = QtWidgets.QCheckBox("Auto axes", self)
        layout1.addWidget(self.autosel)
        self.axes = [QtWidgets.QPushButton(ax, self) for ax in "zxy"]
        [layout1.addWidget(self.axes[i]) for i in [1, 2, 0]]
        layout1.addStretch(1)
        self.clear = QtWidgets.QPushButton("Clear plot", self)
        layout1.addWidget(self.clear)
        self.scale = CapiScale(self)
        self.scale.setFixedHeight(32)
        layout1.addWidget(self.scale)
        layout0.addLayout(layout1)
        layout1 = QtWidgets.QHBoxLayout()
        self.area = QtWidgets.QScrollArea()
        self.area.setWidget(CapiScatter(model))
        self.area.setWidgetResizable(True)
        layout1.addWidget(self.area)
        layout1.addWidget(CapiMap(model))
        layout0.addLayout(layout1)
        widget = QtWidgets.QWidget(self)
        widget.setLayout(layout0)
        widget.setMinimumHeight(400)
        self.setCentralWidget(widget)
        self.pause.stateChanged.connect(lambda:
            self.submit("pause", self.pause.isChecked()))
        self.autosel.stateChanged.connect(lambda:
            self.submit("autosel", self.autosel.isChecked()))
        self.clear.clicked.connect(lambda: self.submit("clear"))
        self.sbind(model, ({}, {}), ["pause", "autosel", "clear", "axes"])
        self.nbind(({}, {}), ["stage", "pause", "autosel", "scale", "axes"])

    def on_stage(self, motors, outputs, state):
        self.axes[0].setFixedWidth((4 + max(len(s) for s in outputs)) * 11)
        nchar = max(len(s) for s in ["(None)"] + motors)
        for widget in self.axes[1:]:
            widget.setFixedWidth((4 + nchar) * 11)
        self.area.widget().setMinimumHeight(len(motors) * 100)
        menus = [QtWidgets.QMenu(self) for widget in self.axes]
        self.actions = [QtWidgets.QActionGroup(menu) for menu in menus]
        for ax, widget, menu, actions, choices in zip(
            "zxy", self.axes, menus, self.actions,
            [outputs, ["(None)",] + motors, ["(None)",] + motors]
        ):
            for i, s in enumerate(choices):
                action = QtWidgets.QAction(s, menu)
                action.setCheckable(True)
                action.triggered.connect((lambda ax, i: lambda:
                    self.submit("axes", ax, i))("zxy".index(ax), i))
                actions.addAction(action)
            menu.addActions(actions.actions())
            actions.actions()[0].setChecked(True)
            widget.setText("%s: %s" % (ax, actions.actions()[0].text()))
            widget.setMenu(menu)
        self.pause.setChecked(state[0])
        self.on_pause(state[0])
        self.autosel.setChecked(state[1])
        self.on_autosel(state[1])

    def on_pause(self, pause):
        self.clear.setEnabled(pause)

    def on_autosel(self, autosel):
        for widget in self.axes:
            widget.setEnabled(not autosel)

    def on_scale(self, lo, hi):
        self.scale.lo.setText("%g" % lo)
        self.scale.hi.setText("%g" % hi)

    def on_axes(self, axes):
        for ax, widget, actions, i in zip("zxy", self.axes, self.actions, axes):
            action = actions.actions()[i]
            action.setChecked(True)
            widget.setText("%s: %s" % (ax, action.text()))

class CapiModel(MambaZModel):
    def __init__(self, name):
        super().__init__()
        self.pause, self.autosel, self.idle = False, True, [True, True, False]
        self.name, (self.mrc, self.mnc) = name, client_build(config_read())
        self.app, self.view = QtWidgets.QApplication([]), CapiView(self)
        self.mnc.subscribe("doc", self.zcb_mk("doc"))
        self.sbind(["idle", "doc", "clear", "pause", "autosel", "axes"])

    def run(self):
        names = self.mrc_req("%s/names" % self.name)["ret"]
        self.axes, self.outputs = [0, 0, 0], names.get("outputs", ["(None)"])
        self.motors = [m.replace(".", "_") for m in names["motors"]]
        self.data = [pandas.DataFrame([[0.0] * (len(self.motors) + 2)])[:0]
            for output in self.outputs]
        self.notify("stage", self.motors, self.outputs,
            (self.pause, self.autosel))
        self.mnc.start()
        self.view.show()
        return self.app.exec_()

    def do_data(self):
        data, axes = self.data[self.axes[0]], self.axes[1:]
        axes = [0, -1] if axes == [0, 0] else axes
        scale = (data.iloc[:,-1].min(), data.iloc[:,-1].max()) \
            if len(data) else (0.0, 0.0)
        self.notify("axes", self.axes)
        self.notify("scale", *scale)
        self.notify("data", data.iloc[:,1:].values)
        self.notify("data2", data.iloc[:,axes + [-1]].values)

    def on_idle(self, i):
        self.idle[i] = True
        if all(self.idle):
            self.idle = [False, False, False]
            self.do_data()

    def on_doc(self, msg):
        if self.pause or msg["typ"][1] != "event":
            return
        data = msg["doc"]["data"]
        try:
            meta = data["meta"]
            output = self.outputs.index(meta["y"]) if "y" in meta else 0
            d = self.data[output]
            d.loc[len(d)] = [len(d)] + [data[k] for k in self.motors + ["eval"]]
            if self.autosel:
                self.axes = [output] + \
                    [self.motors.index(m) + 1 for m in meta["x"]][:2]
        except KeyError:
            return
        if len(self.axes) == 1:
            self.axes += [0, 0]
        elif len(self.axes) == 2:
            self.axes = [self.axes[0], 0, self.axes[1]]
        self.on_idle(2)

    def on_clear(self):
        self.data = [data[:0] for data in self.data]
        self.on_idle(2)

    def on_pause(self, pause):
        self.pause = pause
        self.notify("pause", pause)

    def on_autosel(self, autosel):
        self.autosel = autosel
        self.notify("autosel", autosel)

    def on_axes(self, ax, i):
        if not self.autosel:
            self.axes[ax] = i
        self.on_idle(2)

def main(arg = ""):
    name = arg or "atti_capi"
    sys.exit(CapiModel(name).run())

if __name__ == "__main__":
    main()


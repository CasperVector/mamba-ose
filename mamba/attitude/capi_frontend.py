import numpy
import pandas
import pyqtgraph
import sys
from PyQt5 import QtGui, QtWidgets
from mamba.backend.mzserver import config_read, client_build
from mamba.frontend.utils import MambaZModel, MambaView
from mamba.frontend.pgitems import OptimMap, OptimScatter

class CapiScatter(MambaView, pyqtgraph.GraphicsView):
    def __init__(self, model, parent = None, mtyps = ({}, {})):
        super().__init__(parent)
        self.ci = OptimScatter()
        self.setCentralItem(self.ci)
        self.sbind(model, mtyps, [])
        self.nbind(mtyps, ["stage", "data"])

    def on_stage(self, motors):
        self.ci.doStage(motors)

    def on_data(self, data):
        self.ci.setData(data)

class CapiMap(MambaView, pyqtgraph.GraphicsView):
    def __init__(self, model, parent = None, mtyps = ({}, {})):
        super().__init__(parent)
        self.ci = OptimMap()
        self.setCentralItem(self.ci)
        self.sbind(model, mtyps, [])
        self.nbind(mtyps, ["data2"])

    def on_data2(self, data):
        self.ci.setData(data)

class CapiView(MambaView, QtWidgets.QMainWindow):
    def __init__(self, model, parent = None):
        super().__init__(parent)
        self.setWindowTitle("General attitude tuning")
        layout = QtWidgets.QHBoxLayout()
        self.area = QtWidgets.QScrollArea()
        self.area.setWidget(CapiScatter(model))
        self.area.setWidgetResizable(True)
        layout.addWidget(self.area)
        layout.addWidget(CapiMap(model))
        widget = QtWidgets.QWidget(self)
        widget.setLayout(layout)
        self.setCentralWidget(widget)
        self.sbind(model, ({}, {}), [])
        self.nbind(({}, {}), ["stage"])

    def on_stage(self, motors):
        self.area.widget().setMinimumHeight(len(motors) * 100)

class CapiModel(MambaZModel):
    def __init__(self, name):
        super().__init__()
        self.name, (self.mrc, self.mnc) = name, client_build(config_read())
        self.app, self.view = QtWidgets.QApplication([]), CapiView(self)
        self.mnc.subscribe("doc", self.zcb_mk("doc"))
        self.sbind(["doc"])

    def run(self):
        self.motors = self.mrc_req("%s/names" % self.name)["ret"][1]
        self.data = pandas.DataFrame([[0.0] * (len(self.motors) + 2)])[:0]
        self.notify("stage", self.motors)
        self.mnc.start()
        self.view.show()
        return self.app.exec_()

    def on_doc(self, msg):
        if msg["typ"][1] != "event":
            return
        data = msg["doc"]["data"]
        try:
            meta = data["meta"]
            self.data.loc[len(self.data)] = [len(self.data)] + \
                [data[k] for k in self.motors + ["eval"]]
            idx = [self.motors.index(m) + 1 for m in meta["x"]][:2]
        except KeyError:
            return
        if not idx:
            idx = [0, -1]
        elif len(idx) == 1:
            idx = [0] + idx
        self.notify("data", self.data.iloc[:,1:].values)
        self.notify("data2", self.data.iloc[:,idx + [-1]].values)

def main(arg = ""):
    name = arg or "atti_capi"
    sys.exit(CapiModel(name).run())

if __name__ == "__main__":
    main()


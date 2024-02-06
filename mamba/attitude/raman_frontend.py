import numpy
import pandas
import pyqtgraph
import sys
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt
from mamba.backend.zserver import ZError
from mamba.backend.mzserver import config_read, client_build
from mamba.frontend.utils import MambaZModel, MambaView, \
    DragTableView, DragTableModel, PandasMMixin, DragTable
from mamba.frontend.pgitems import \
    MyImageItem, MyPlotItem, MultiRois, ThumbLines, MyImageView
from .common import norm_xywh, xywhs2rois

def rot2perm(src, dest, n):
    perm, (lo, hi) = list(range(n)), sorted([src, dest])
    sign, hi = -1 if dest < src else 1, hi + 1
    for i in range(hi - lo):
        perm[lo + i] = lo + (i + sign) % (hi - lo)
    return perm, (lo, hi)

def perm_apply(perm, orig = None):
    return [orig[perm[i]] for i in range(len(perm))] if orig else perm

def palette_mk(n):
    return [pyqtgraph.hsvColor(i / n, sat = s).getRgb()[:3]
        for i in range(int(numpy.ceil(n / 2))) for s in (1.0, 0.33)][:n]

class RamanMLines(MambaView, pyqtgraph.GraphicsView):
    def __init__(self, model, parent = None, mtyps = ({}, {})):
        super().__init__(parent)
        self.ci = MyPlotItem()
        self.setCentralItem(self.ci)
        self.sbind(model, mtyps, [])
        self.nbind(mtyps, ["stage", "pens", "lines"])

    def on_stage(self, nanal):
        self.lines = [self.ci.plot() for _ in range(nanal)]

    def on_pens(self, pens):
        for line, pen in zip(self.lines, pens):
            line.setPen(pyqtgraph.mkPen(color = pen[0], width = 2))
            line.setVisible(pen[1])

    def on_lines(self, xx, yy):
        for line, xs, ys in zip(self.lines, xx, yy):
            line.setData(xs, ys)

class RamanTLines(MambaView, pyqtgraph.GraphicsView):
    def __init__(self, model, parent = None, mtyps = ({}, {})):
        super().__init__(parent)
        self.ci = ThumbLines()
        self.setCentralItem(self.ci)
        self.sbind(model, mtyps, [])
        self.nbind(mtyps, ["stage", "pens", "lines"])

    def on_stage(self, nanal):
        self.ci.doStage(nanal, 5, transpose = True)

    def on_pens(self, pens):
        for line, pen in zip(self.ci.lines, pens):
            line.setPen(pyqtgraph.mkPen(color = pen[0], width = 2))

    def on_lines(self, xx, yy):
        for line, xs, ys in zip(self.ci.lines, xx, yy):
            line.setData(xs, ys)

class RamanImage(MambaView, pyqtgraph.GraphicsView):
    def __init__(self, model, parent = None, mtyps = ({}, {})):
        super().__init__(parent)
        self.ci = MyImageView(view = MultiRois())
        self.ci.lut.setColorMap("CET-L16")
        self.setCentralItem(self.ci)
        self.on_img = self.ci.setImage
        self.sbind(model, mtyps, ["roi"])
        self.nbind(mtyps, ["stage", "img", "rois", "roi"])

    def on_stage(self, nanal):
        self.ci.view.doStage(nanal)
        self.rois = self.ci.view.rois
        for i, roi in enumerate(self.rois):
            roi.sigRegionChangeFinished.connect\
                ((lambda i: lambda: self.submit_roi(i))(i))

    def on_rois(self, rois):
        [self.on_roi(i, xywh) for i, xywh in enumerate(rois)]

    def on_roi(self, i, xywh):
        self.rois[i].setXywh(xywh)

    def submit_roi(self, i):
        self.submit("roi", i, self.rois[i].getXywh())

class RamanTableV(DragTableView):
    def sizeHint(self):
        return QtCore.QSize(640, 480)

    def markDrag(self, src, dest = None):
        if dest and src[0] == dest[0]:
            return False
        idx = dest or src
        self.selectionModel().select(QtCore.QItemSelection(
            self.model().createIndex(idx[0], self.wrapper.model.colid("x")),
            self.model().createIndex(idx[0], self.model().columnCount() - 1),
        ), QtCore.QItemSelectionModel.ClearAndSelect)
        if dest:
            return True

class RamanTableM(PandasMMixin, DragTableModel):
    def columnCount(self, parent = None):
        return self.wrapper.model.colid("pen")

    def flags(self, index):
        ret = Qt.ItemIsEnabled | Qt.ItemIsDropEnabled | \
            (Qt.ItemIsEditable if self.isEditable(index) else 0)
        if index.column() > self.wrapper.model.colid("x2"):
            ret |= Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
        return ret

class RamanView(MambaView, QtWidgets.QMainWindow):
    first = False

    def __init__(self, model, parent = None):
        super().__init__(parent)
        self.setWindowTitle("Attitude tuning for XRS analysers")
        self.actions = {}
        toolbar = QtWidgets.QToolBar()
        for typ, desc in [
            ("auto_rois", "ROI detection"),
            ("begin_perm", "ROI matching"),
            ("begin_focus", "Focus tuning"),
            ("refresh", "Refresh data"),
            ("begin_commit", "Commit changes"),
            ("stop", "Stop motors")
        ]:
            item = QtWidgets.QAction(desc, self)
            item.triggered.connect((lambda typ: lambda: self.submit(typ))(typ))
            toolbar.addAction(item)
            self.actions[typ] = item
        self.addToolBar(toolbar)
        self.table = DragTable(model)
        self.table.qbind(RamanTableM(model.table), RamanTableV())
        for item, right, desc in [
            (RamanImage(model), 0, "Image from the detector"),
            (RamanMLines(model), 0, "Evaluation functions"),
            (self.table.qview, 1, "Analyser information"),
            (RamanTLines(model), 1, "Function thumbnails")
        ]:
            dock = QtWidgets.QDockWidget(desc, self)
            dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFloatable |
                QtWidgets.QDockWidget.DockWidgetMovable)
            dock.setWidget(item)
            self.addDockWidget(Qt.RightDockWidgetArea
                if right else Qt.LeftDockWidgetArea, dock)
        self.sbind(model, ({}, {}), ["auto_rois", "begin_perm",
            "begin_focus", "refresh", "begin_commit", "stop"])
        self.nbind(({}, {}), ["mode"])

    def on_mode(self, mode, allowed):
        if not self.first:
            for i in range(self.table.qmodel.columnCount()):
                self.table.qview.setColumnWidth(i, 80)
            self.first = True
        [v.setEnabled(k in allowed) for k, v in self.actions.items()]

class RamanModel(MambaZModel):
    modes = {
        "unstaged": ["auto_rois"], "staged": ["auto_rois",
            "begin_perm", "begin_focus", "refresh", "edit"],
        "edit": ["begin_commit", "refresh"],
        "commit": ["stop"], "perm": ["stop"], "focus": ["stop"]
    }

    def __init__(self, name):
        super().__init__()
        self.table = pandas.DataFrame(columns =
            ["show", "x0", "x1", "x2", "x", "y", "w", "h", "pen"])
        self.img_name = self.dim = self.motors = self.nanal = self.mdict = \
            self.xx = self.yy = self.delta = self.perm = None
        self.name, (self.mrc, self.mnc) = name, client_build(config_read())
        self.app, self.view = QtWidgets.QApplication([]), RamanView(self)
        self.mnc.subscribe("doc", self.zcb_mk("doc"))
        self.mnc.subscribe("monitor", self.zcb_mk("monitor"))
        self.sbind([
            "monitor", "doc", "cell", "tdrag", "roi", "refresh",
            "stop", "begin_commit", "end_commit", "auto_rois",
            "begin_perm", "end_perm", "begin_focus", "end_focus"
        ])
        self.do_mode("unstaged")

    def run(self):
        self.mnc.start()
        self.view.showMaximized()
        self.view.show()
        return self.app.exec_()

    def allowed(self):
        return self.modes[self.mode]

    def do_mode(self, mode):
        self.mode = mode
        self.notify("mode", mode, self.allowed())

    def do_new_lines(self):
        self.xx = pandas.DataFrame(columns = list(range(self.nanal)))
        self.yy = pandas.DataFrame(columns = list(range(self.nanal)))

    def do_lines(self):
        self.notify("lines", self.xx.values.T.tolist(),
            self.yy.values.T.tolist())

    def colid(self, name):
        return self.table.columns.get_loc(name)

    def on_monitor(self, msg):
        if self.mode == "unstaged":
            return
        elif msg["typ"][1] == "position":
            if self.mode == "edit":
                return
            for k, v in msg["doc"]["data"].items():
                k = self.mdict.get(k)
                if k:
                    self.table.iat[k] = v
                    self.notify("cells", *k)
        elif msg["typ"][1] == "image":
            img = msg["doc"]["data"].get(self.img_name)
            if img is not None:
                self.notify("img", img)

    def on_doc(self, msg):
        if msg["typ"][1] != "event" or self.mode == "unstaged":
            return
        data = msg["doc"]["data"]
        try:
            img = data[self.img_name]
            self.table.loc[:, "x0" : "x2"] = [[data[self.motors[3 * i + j]]
                for j in range(3)] for i in range(self.nanal)]
        except KeyError:
            return
        def append(table, data):
            table.loc[len(table),:] = data
        self.notify("img", img)
        if self.mode in ["perm", "focus"]:
            append(self.xx, len(self.xx) if self.mode == "perm" else
                [data[self.motors[3 * i]] for i in range(self.nanal)])
            append(self.yy, data["eval"])
            self.do_lines()
        self.notify("cells", 0, self.colid("x0"), -1, self.colid("x2"))

    def do_pens(self, i = None):
        if i is None:
            i, j = 0, -1
        else:
            j = i
        self.notify("pens", self.table.loc[:, ["pen", "show"]].values)
        self.notify("cells", i, self.colid("show"), j, self.colid("show"))

    def do_stage(self):
        names = self.mrc_req("%s/names" % self.name)["ret"]
        self.dim, (self.img_name,), self.motors = \
            names["dim"], names["dets"], names["motors"]
        self.img_name = self.img_name.replace(".", "_") + "_image"
        self.motors = [m.replace(".", "_") for m in self.motors]
        self.nanal = len(self.motors) // 3
        self.mdict = dict((self.motors[3 * i + j], (i, j + self.colid("x0")))
            for i in range(self.nanal) for j in range(3))
        self.table.loc[:, "pen"] = palette_mk(self.nanal)
        self.table.loc[:, "show"] = True
        self.notify("stage", self.nanal)
        self.do_pens()
        self.notify("treset")
        self.do_mode("staged")

    def do_edit(self):
        self.delta = pandas.DataFrame({
            "pos": [[None] * 3 for _ in range(self.nanal)],
            "xywh": [numpy.nan] * self.nanal
        }, dtype = "object")
        self.do_mode("edit")

    def do_maybe_edit(self):
        if "edit" in self.allowed():
            self.do_edit()
        return self.mode == "edit"

    def on_cell(self, i, j, data):
        if j < self.colid("x0"):
            self.table.at[i, "show"] = data
            self.do_pens(i)
        elif j > self.colid("x2"):
            xywh = list(self.table.loc[i, "x" : "h"])
            xywh[j - self.colid("x")] = data
            self.on_roi(i, tuple(xywh))
        else:
            if self.do_maybe_edit():
                self.delta.at[i, "pos"][j - self.colid("x0")] = \
                    self.table.iat[i, j] = data
            self.notify("cells", i, j)

    def do_rois(self, i = None):
        if i is None:
            self.notify("rois", list(map(tuple,
                self.table.loc[:, "x" : "h"].values)))
            self.notify("cells", 0, self.colid("x"), -1, self.colid("h"))
        else:
            self.notify("roi", i, tuple(self.table.loc[i, "x" : "h"]))
            self.notify("cells", i, self.colid("x"), i, self.colid("h"))

    def on_tdrag(self, src, dest):
        if self.do_maybe_edit():
            perm, (lo, hi) = rot2perm(src[0], dest[0], self.nanal)
            self.perm = perm_apply(perm, self.perm)
            self.table.loc[list(range(lo, hi)), "x" : "h"] = \
                self.table.loc[perm[lo : hi], "x" : "h"].values.tolist()
            self.delta.loc[list(range(lo, hi)), "xywh"] = \
                self.delta.loc[perm[lo : hi], "xywh"].values.tolist()
        self.do_rois()

    def on_roi(self, i, xywh):
        if self.do_maybe_edit():
            self.table.loc[i, "x" : "h"] = \
                self.delta.at[i, "xywh"] = norm_xywh(xywh, *self.dim)
        self.do_rois(i)

    def do_refresh(self, roi = False):
        ret = self.mrc_cmd("U.%s.refresh(%s)\n" %
            (self.name, "roi = True" if roi else ""))["ret"]
        self.table.loc[:, "x" : "h"] = \
            self.mrc_req("%s/rois" % self.name)["ret"]
        self.do_rois()
        return ret

    def on_auto_rois(self):
        if self.mode == "unstaged":
            self.do_stage()
        self.do_new_lines()
        self.do_lines()
        err = self.do_refresh(roi = True)
        if err:
            self.do_err("Warning", "Found %d less than expected ROIs." % err)

    def on_refresh(self):
        self.do_refresh()
        if self.mode == "edit":
            self.delta = self.perm = None
            self.do_mode("staged")

    def on_stop(self):
        self.mrc_cmd("U.%s.stop()\n" % self.name)

    def on_begin_commit(self):
        if self.perm:
            self.mrc_cmd("U.%s.perm_rois(%r)\n" % (self.name, self.perm))
            if len(self.xx):
                self.xx.iloc[:,:] = self.xx.iloc[:,self.perm].values.tolist()
                self.yy.iloc[:,:] = self.yy.iloc[:,self.perm].values.tolist()
                self.do_lines()
        data = self.delta.xywh.dropna()
        if len(data):
            self.mrc_cmd("U.%s.set_rois(%r, %r)\n" %
                (self.name, xywhs2rois(data), list(data.index)))
        data = [(x, 3 * i + j) for i, pos in enumerate(self.delta.pos)
            for j, x in enumerate(pos) if x is not None]
        if data:
            self.do_mode("commit")
            self.mrc_go("end_commit", "%%go U.%s.put_x(%r, %r)\n" %
                ((self.name,) + tuple(zip(*data))))
        else:
            self.on_end_commit()

    def on_end_commit(self, rep = None):
        self.do_refresh()
        self.delta = self.perm = None
        self.do_mode("staged")
        if rep:
            self.rep_chk(rep)

    def on_begin_perm(self):
        self.do_mode("perm")
        self.do_new_lines()
        self.mrc_go("end_perm", "%%go U.%s.auto_perm()\n" % self.name)

    def on_end_perm(self, rep):
        try:
            err, perm = self.rep_chk(rep)["ret"]
        except ZError:
            self.do_mode("staged")
            raise
        self.xx.iloc[:,:] = self.xx.iloc[:,perm].values.tolist()
        self.yy.iloc[:,:] = self.yy.iloc[:,perm].values.tolist()
        self.do_lines()
        self.table.loc[:, "x" : "h"] = \
            self.table.loc[perm, "x" : "h"].values.tolist()
        self.do_rois()
        self.do_mode("staged")
        if err:
            self.do_err("Warning", "No match for analysers %r." % err)

    def on_begin_focus(self):
        self.do_mode("focus")
        self.do_new_lines()
        self.mrc_go("end_focus", "%%go U.%s.auto_focus()\n" % self.name)

    def on_end_focus(self, rep):
        self.do_mode("staged")
        err = self.rep_chk(rep)["ret"]
        if err:
            self.do_err("Warning", "Focusing failed for analysers %r." % err)

def main(arg = ""):
    name = arg or "atti_raman"
    sys.exit(RamanModel(name).run())

if __name__ == "__main__":
    main()


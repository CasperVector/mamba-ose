import numpy
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import QStyle
from ..backend.zserver import ZError, zsv_rep_chk, zsv_err_fmt

def slot_gen(obj, typs0, typs1):
    handles = {typs0.get(typ, typ): getattr(obj, "on_" + typ) for typ in typs1}
    def slot(args):
        hdl = handles.get(args[0])
        hdl and hdl(*args[1:])
    return slot

class MambaModel(QtCore.QObject):
    sigSubmit, sigNotify = QtCore.pyqtSignal(tuple), QtCore.pyqtSignal(tuple)
    submit = lambda self, *args: self.sigSubmit.emit(args)
    notify = lambda self, *args: self.sigNotify.emit(args)
    def sbind(self, styps):
        self.sigSubmit.connect(slot_gen(self, {}, styps))

class MambaZModel(MambaModel):
    zcb_mk = lambda self, typ: lambda msg: self.submit(typ, msg)
    mrc_req = lambda self, *args, **kwargs: \
        self.rep_chk(self.mrc.req_rep_base(*args, **kwargs))
    mrc_cmd = lambda self, cmd: self.mrc_req("cmd", cmd = cmd)
    mrc_go = lambda self, end, cmd: \
        self.mrc.do_cmd(cmd).subscribe(self.zcb_mk(end))

    def do_err(self, title, desc):
        QtWidgets.QMessageBox.warning(self.view, title, desc)

    def rep_chk(self, rep):
        try:
            return zsv_rep_chk(rep)
        except ZError as e:
            self.do_err("ZError", zsv_err_fmt(e))
            raise

class MambaView(object):
    def sbind(self, model, mtyps, styps):
        self.model = model
        self.styps = {typ: mtyps[0].get(typ, typ) for typ in styps}

    def nbind(self, mtyps, ntyps):
        self.model.sigNotify.connect(slot_gen(self, mtyps[1], ntyps))

    def submit(self, typ, *args):
        self.model.submit(self.styps[typ], *args)

class MyItemDelegate(QtWidgets.QStyledItemDelegate):
    bSize = 13

    def bRect(self, option, index):
        align = index.data(Qt.TextAlignmentRole) \
            or Qt.AlignHCenter | Qt.AlignVCenter
        return QStyle.alignedRect(option.direction, align,
            QtCore.QSize(self.bSize, self.bSize), option.rect)

    def paint(self, painter, option, index):
        data = index.data(Qt.EditRole)
        if not numpy.issubdtype(type(data), numpy.bool_):
            return super().paint(painter, option, index)
        option = QtWidgets.QStyleOptionViewItem(option)
        style = option.widget.style()
        style.drawPrimitive(QStyle.PE_PanelItemViewItem,
            option, painter, option.widget)
        option.state |= QStyle.StateFlag.State_Enabled \
            if index.flags() & Qt.ItemIsEditable else \
            QStyle.StateFlag.State_ReadOnly
        option.state |= QStyle.StateFlag.State_On \
            if data else QStyle.StateFlag.State_Off
        option.rect = self.bRect(option, index)
        style.drawPrimitive(QStyle.PE_IndicatorItemViewItemCheck,
            option, painter, option.widget)

    def editorEvent(self, event, model, option, index):
        data = index.data(Qt.EditRole)
        if not numpy.issubdtype(type(data), numpy.bool_):
            return super().editorEvent(event, model, option, index)
        if event.type() in [QEvent.MouseButtonPress,
            QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick]:
            if not (event.button() == Qt.LeftButton and
                self.bRect(option, index).contains(event.pos())):
                return False
            if event.type() != QEvent.MouseButtonRelease:
                return True
        elif event.type() == QEvent.KeyPress:
            if event.key() not in [Qt.Key_Space, Qt.Key_Select]:
                return False
        else:
            return False
        if index.flags() & Qt.ItemIsEditable:
            model.setData(index, not data, role = Qt.EditRole)
        return True

    def createEditor(self, parent, option, index):
        data = index.data(Qt.EditRole)
        typ = type(data)
        if numpy.issubdtype(typ, numpy.bool_):
            return None
        if not any(numpy.issubdtype(typ, dtype) for dtype in
            [numpy.integer, numpy.floating, numpy.complex_]):
            return super().createEditor(parent, option, index)
        return QtWidgets.QLineEdit(parent)

    def setEditorData(self, editor, index):
        data = index.data(Qt.EditRole)
        typ = type(data)
        if not any(numpy.issubdtype(typ, dtype) for dtype in
            [numpy.integer, numpy.floating, numpy.complex_]):
            return super().setEditorData(editor, index)
        editor.setText(str(data))

    def setModelData(self, editor, model, index):
        typ = type(index.data(Qt.EditRole))
        if not any(numpy.issubdtype(typ, dtype) for dtype in
            [numpy.integer, numpy.floating, numpy.complex_]):
            return super().setModelData(editor, model, index)
        try:
            data = typ(editor.text())
        except ValueError:
            pass
        else:
            model.setData(index, data, role = Qt.EditRole)

class MyTableView(QtWidgets.QTableView):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setItemDelegate(MyItemDelegate())

class DragTableView(MyTableView):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setSelectionMode(self.SingleSelection)
        self.setDragDropMode(self.InternalMove)

    def markDrag(self, src, dest = None):
        if dest:
            return src != dest

    def dragEnterEvent(self, event):
        sel = self.selectedIndexes()
        if sel:
            src = sel[0].row(), sel[0].column()
            if 0 <= src[0] < self.model().rowCount() and \
                0 <= src[1] < self.model().columnCount():
                self.markDrag(src)
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        sel = self.selectedIndexes()
        if sel:
            src, dest = sel[0], self.indexAt(event.pos())
            src, dest = (src.row(), src.column()), (dest.row(), dest.column())
            size = self.model().rowCount(), self.model().columnCount()
            if 0 <= src[0] < size[0] and 0 <= src[1] < size[1] \
                and 0 <= dest[0] < size[0] and 0 <= dest[1] < size[1] \
                and self.markDrag(src, dest):
                self.wrapper.submit("tdrag", src, dest)
                event.accept()

class MyTableModel(QtCore.QAbstractTableModel):
    def setData(self, index, data, role = None):
        if role == Qt.EditRole and self.flags(index) & Qt.ItemIsEditable:
            self.wrapper.submit("cell", index.row(), index.column(), data)
        return False

    def isEditable(self, index):
        return True

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | \
            (Qt.ItemIsEditable if self.isEditable(index) else 0)

class DragTableModel(MyTableModel):
    def supportedDropActions(self):
        return Qt.MoveAction

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | \
            Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled | \
            (Qt.ItemIsEditable if self.isEditable(index) else 0)

class MyTableMMixin(QtCore.QAbstractTableModel):
    def __init__(self, table, parent = None):
        super().__init__(parent)
        self.table = table

    def rowCount(self, parent = None):
        return len(self.table)

    def headerData(self, section, orientation, role = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation in [Qt.Vertical, Qt.Horizontal]:
            return section

    def cell(self, index):
        return self.table[index.row()][index.column()]

    def data(self, index, role = None):
        if role in (Qt.DisplayRole, Qt.EditRole):
            data = self.cell(index)
            if role == Qt.DisplayRole:
                data = str(data)
            return data

    def isEditable(self, index):
        return index.data(Qt.EditRole) is not None

class PandasMMixin(MyTableMMixin):
    def columnCount(self, parent = None):
        return len(self.table.columns)

    def headerData(self, section, orientation, role = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Vertical:
            return section
        if orientation == Qt.Horizontal:
            return self.table.columns[section]

    def cell(self, index):
        return self.table.iat[index.row(), index.column()]

    def isEditable(self, index):
        data = index.data(Qt.EditRole)
        return not (data is None or numpy.isnan(data) is numpy.bool_(True))

class MambaTable(MambaView):
    viewClass = MyTableView
    sbinds, nbinds = ["cell"], ["cells", "treset"]

    def __init__(self, model, mtyps = ({}, {})):
        self.sbind(model, ({}, {}), self.sbinds)
        self.nbind(({}, {}), self.nbinds)

    def qbind(self, qmodel, qview = None):
        self.qmodel, self.qview = qmodel, qview or self.viewClass()
        self.qmodel.wrapper = self.qview.wrapper = self
        self.qview.setModel(qmodel)

    def on_cells(self, i0, j0, i1 = None, j1 = None):
        qmodel = self.qmodel
        ii = [i0, i0 if i1 is None else i1]
        jj = [j0, j0 if j1 is None else j1]
        for i in range(2):
            if ii[i] < 0:
                ii[i] += qmodel.rowCount()
            if jj[i] < 0:
                jj[i] += qmodel.columnCount()
        self.qmodel.dataChanged.emit(*(self.qmodel.createIndex(i, j)
            for i, j in zip(sorted(ii), sorted(jj))))

    def on_treset(self):
        self.qmodel.endResetModel()

class DragTable(MambaTable):
    viewClass = DragTableView
    sbinds = MambaTable.sbinds + ["tdrag"]


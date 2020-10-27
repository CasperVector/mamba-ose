from functools import partial

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame,
                             QDialog, QGridLayout, QLabel, QSizePolicy,
                             QLineEdit, QPushButton, QColorDialog, QTableWidget,
                             QTableWidgetItem)
from PyQt5.QtCore import QSize, QEventLoop, Qt
from PyQt5.QtGui import QPixmap, QIcon, QColor
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure

import mamba_client
from mamba_client.data_client import DataClientI


DEFAULT_COLOR = QColor("blue")


class PlotWidget(QWidget):
    def __init__(self, data_client: DataClientI):
        super().__init__()
        self.data_client = data_client
        self.logger = mamba_client.logger
        self.layout = QVBoxLayout(self)
        self.figure = Figure(figsize=(4, 2))
        self.canvas = FigureCanvas(self.figure)
        self.navbar = NavigationToolbar(self.canvas, self)
        self.navbar.setIconSize(QSize(15, 15))

        a = self.navbar.addAction(self._icon(':/icons/link.png'),
                                  "Select Data Source",
                                  self.show_data_source_dialog)

        self.layout.addWidget(self.navbar)
        self.layout.addWidget(self.canvas)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.axs = self.figure.subplots()
        self.figure.set_tight_layout(True)
        self.legend = self.figure.legend()

        self.data_sets = {}
        self.xsource = ""
        self.lines = {}

        self.scanning = False

        self.registered_data_callbacks = []

    def register_scan_stop_cbk(self):
        for name in ["__scan_ended"]:
            cbk = partial(self.update_data, name)
            self.registered_data_callbacks.append(cbk)
            self.data_client.request_data(name, cbk)

    @staticmethod
    def _icon(path):
        pm = QPixmap(path)
        return QIcon(pm)

    @classmethod
    def get_init_func(cls, data_client):
        return lambda: cls(data_client)

    def show_data_source_dialog(self):
        data_source_select_dialog = PlotDataSelectDialog(
            self,
            [(name, data_set['qcolor'])
             for name, data_set in self.data_sets.items()]
        )

        ret = data_source_select_dialog.display()
        if not ret:
            return

        names, colors, self.xsource = ret

        for cbk in self.registered_data_callbacks:
            self.data_client.stop_requesting_data(cbk)
        self.register_scan_stop_cbk()

        for name, color in zip(names, colors):
            if name not in self.data_sets:
                cbk = partial(self.update_data, name)
                self.registered_data_callbacks.append(cbk)
                self.data_client.request_data(name, cbk)
                self.data_sets[name] = {
                    'data': [],
                    'timestamp': [],
                    'label': name,
                }
            color_hex = hex(color.rgba())
            self.data_sets[name]['color'] = "#" + color_hex[4:] + color_hex[2:4]
            self.data_sets[name]['qcolor'] = color

    def update_data(self, name, _id, value, timestamp):
        if value is None:
            if not self.scanning:
                self.scanning = True
                self.figure.clf()
                self.axs = self.figure.subplots()
                self.figure.set_tight_layout(True)
                self.legend = self.figure.legend()

                for name in self.data_sets:
                    self.data_sets[name]['data'] = []
                    self.data_sets[name]['timestamp'] = []
                    if name in self.lines:
                        for line in self.lines[name]:
                            line.remove()
                        self.lines[name] = []

                if self.xsource:
                    self.axs.set_xlabel(self.xsource)
                else:
                    self.axs.set_xlabel("Time")
            elif name == "__scan_ended":
                self.scanning = False
        else:
            self.data_sets[name]['data'].append(value)
            self.data_sets[name]['timestamp'].append(timestamp)

        if self.xsource:
            x_len = len(self.data_sets[self.xsource]['data'])
            for dataset in self.data_sets.values():
                #  wait for all data to be at the same length
                if x_len > len(dataset['data']):
                    return
        self.plot()

    def plot(self):
        self.legend.remove()
        for name, data_set in self.data_sets.items():
            if name == self.xsource:
                continue

            if name in self.lines:
                for line in self.lines[name]:
                    line.remove()

            if self.xsource:
                x_len = len(self.data_sets[self.xsource]['data'])
                self.lines[name] = self.axs.plot(
                    self.data_sets[self.xsource]['data'],
                    data_set['data'][:x_len],
                    color=data_set['color'],
                    label=data_set['label']
                )
            else:
                self.lines[name] = self.axs.plot(
                    data_set['timestamp'],
                    data_set['data'],
                    color=data_set['color'],
                    label=data_set['label']
                )

        self.legend = self.figure.legend()
        self.canvas.draw()

    def __del__(self):
        for cbk in self.registered_data_callbacks:
            self.data_client.stop_requesting_data(cbk)


NAME_COL = 0
X_COL = 1
COLOR_COL = 2


class PlotDataSelectDialog(QDialog):
    def __init__(self, parent=None, source_color_pair=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Data Source")
        self.colors = []
        self.source_names = []
        self.x_source = ""

        self.color = DEFAULT_COLOR

        data_name_label = QLabel("Data source list")

        self.name_table_widget = QTableWidget()
        self.name_table_widget.setRowCount(0)
        self.name_table_widget.setColumnCount(3)

        self.name_table_widget.setHorizontalHeaderItem(
            NAME_COL, QTableWidgetItem("Data source"))
        self.name_table_widget.setHorizontalHeaderItem(
            X_COL, QTableWidgetItem("As X-axis"))
        self.name_table_widget.setHorizontalHeaderItem(
            COLOR_COL, QTableWidgetItem("Color"))

        name_label = QLabel("Data source")
        self.name_line_edit = QLineEdit()
        self.color_dia = QColorDialog(self.color)
        self.line_color_select = QPushButton()
        self.line_color_select.setSizePolicy(QSizePolicy.Fixed,
                                             QSizePolicy.Fixed)
        self.line_color_select.clicked.connect(self.select_color_clicked)
        self.line_color_pixmap = QPixmap(10, 10)
        self.line_color_pixmap.fill(self.color)
        self.line_color_select.setIcon(QIcon(self.line_color_pixmap))

        self.ok_btn = QPushButton("OK")
        self.delete_btn = QPushButton()
        self.add_btn = QPushButton()
        self.ok_btn.clicked.connect(self.ok_clicked)
        self.add_btn.clicked.connect(self.add_clicked)
        self.delete_btn.clicked.connect(self.delete_clicked)

        sep_line = QFrame()
        sep_line.setFrameShape(QFrame.HLine)
        sep_line.setFrameShadow(QFrame.Sunken)

        self.layout = QGridLayout()
        self.layout.addWidget(data_name_label, 0, 0, 1, 4)
        self.layout.addWidget(self.name_table_widget, 1, 0, 1, 4)
        self.layout.addWidget(self.delete_btn, 2, 3)

        self.layout.addWidget(sep_line, 3, 0, 1, 4)

        self.layout.addWidget(name_label, 4, 0)
        self.layout.addWidget(self.name_line_edit, 4, 1)
        self.layout.addWidget(self.line_color_select, 4, 2)
        self.layout.addWidget(self.add_btn, 4, 3)
        self.layout.addWidget(self.ok_btn, 5, 3)

        self.setLayout(self.layout)

        for btn, (pix, size) in [
            (self.ok_btn, (QPixmap(":/icons/checkmark.png"), 0)),
            (self.delete_btn, (QPixmap(":/icons/delete.png"), 0)),
            (self.add_btn, (QPixmap(":/icons/list-add.png"), 0))
        ]:
            icon = QIcon(pix)
            btn.setIcon(icon)
            if size > 0:
                btn.setIconSize(QSize(size, size))

        self.name_table_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff)

        for source, color in source_color_pair:
            self.add_source(source, color)

    def resizeEvent(self, evt):
        self.resize_col()
        self.ok_btn.setFocus()

    def resize_col(self):
        width = self.name_table_widget.width()
        self.name_table_widget.setColumnWidth(NAME_COL, int(width * 0.6))
        self.name_table_widget.setColumnWidth(X_COL, int(width * 0.2))
        self.name_table_widget.setColumnWidth(COLOR_COL, int(width * 0.2))

    def select_color_clicked(self):
        self.color = self.color_dia.getColor(self.color)

        self.raise_()
        self.activateWindow()

        self.line_color_pixmap.fill(self.color)
        self.line_color_select.setIcon(QIcon(self.line_color_pixmap))

    def add_clicked(self):
        source = self.name_line_edit.text()

        if source:
            color = self.color
            self.add_source(source, color)

    def delete_clicked(self):
        row = self.name_table_widget.currentRow()
        self.name_table_widget.removeRow(row)
        del self.source_names[row]
        del self.colors[row]

    def add_source(self, source, color, xaxis=False):
        new_row = self.name_table_widget.rowCount()
        self.name_table_widget.insertRow(new_row)

        self.name_table_widget.setItem(new_row, NAME_COL,
                                       self._get_table_uneditable_item(source))
        self.name_table_widget.setItem(new_row, X_COL,
                                       self._get_table_checkbox_item(xaxis))

        if xaxis and self.x_source != source:
            if self.x_source:
                i = self.source_names.index(self.x_source)
                self.name_table_widget.item(i, X_COL).setCheckState(
                    Qt.Unchecked)
            self.x_source = source

        pix = QPixmap(10, 10)
        pix.fill(color)
        self.name_table_widget.setItem(new_row, COLOR_COL,
                                       self._get_table_icon_item(
                                           QIcon(pix)))
        self.source_names.append(source)
        self.colors.append(color)

        self.resize_col()

    def ok_clicked(self):
        self.done(QDialog.Accepted)

    def display(self):
        if self.exec() == QDialog.Accepted:
            for i in range(self.name_table_widget.rowCount()):
                if self.name_table_widget.item(i, X_COL).checkState() == Qt.Checked:
                    self.x_source = self.source_names[i]

            return self.source_names, self.colors, self.x_source
        else:
            return []

    @staticmethod
    def _get_table_uneditable_item(text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    @staticmethod
    def _get_table_checkbox_item(checked=False):
        item = QTableWidgetItem()
        if checked:
            item.setCheckState(Qt.Checked)
        else:
            item.setCheckState(Qt.Unchecked)

        return item

    @staticmethod
    def _get_table_icon_item(icon):
        item = QTableWidgetItem()
        item.setIcon(icon)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        item.setTextAlignment(Qt.AlignCenter)
        return item

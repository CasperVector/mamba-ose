from functools import partial

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QDialog, QGridLayout, QLabel,
                             QLineEdit, QPushButton, QColorDialog)
from PyQt5.QtCore import QSize, QEventLoop
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
        self.lines = {}

        self.scanning = False

        self.registered_data_callbacks = []

    @staticmethod
    def _icon(path):
        pm = QPixmap(path)
        return QIcon(pm)

    @classmethod
    def get_init_func(cls, data_client):
        return lambda: cls(data_client)

    def show_data_source_dialog(self):
        data_source_select_dialog = PlotDataSelectDialog(self)
        name, color = data_source_select_dialog.display()
        if name:
            if name not in self.data_sets:
                cbk = partial(self.update_data, name)
                self.registered_data_callbacks.append(cbk)
                self.data_client.request_data(name, cbk)
                self.data_sets[name] = {
                    'x': [],
                    'y': [],
                    'label': name,
                }
            color_hex = hex(color.rgba())
            self.data_sets[name]['color'] = "#" + color_hex[4:] + color_hex[2:4]

    def update_data(self, name, value, timestamp):
        assert name in self.data_sets
        if value is None:
            if not self.scanning:
                self.scanning = True
                self.data_sets[name]['x'] = []
                self.data_sets[name]['y'] = []
                if name in self.lines:
                    for line in self.lines[name]:
                        line.remove()
                self.lines[name] = []
            else:
                self.scanning = False
        else:
            self.data_sets[name]['x'].append(timestamp)
            self.data_sets[name]['y'].append(value)
        self.plot()

    def plot(self):
        self.legend.remove()
        for name, data_set in self.data_sets.items():
            for line in self.lines[name]:
                line.remove()
            self.lines[name] = self.axs.plot(
                data_set['x'],
                data_set['y'],
                color=data_set["color"],
                label=data_set['label']
            )
        self.legend = self.figure.legend()
        self.canvas.draw()

    def __del__(self):
        for cbk in self.registered_data_callbacks:
            self.data_client.stop_requesting_data(cbk)


class PlotDataSelectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Data Source")
        self.color = DEFAULT_COLOR

        data_name_label = QLabel("Data name")
        self.name_line_edit = QLineEdit()

        self.color_dia = QColorDialog(self.color)
        color_select_label = QLabel("Line Color")
        self.line_color_select = QPushButton("Select...")
        self.line_color_select.clicked.connect(self.select_color_clicked)
        self.line_color_pixmap = QPixmap(10, 10)
        self.line_color_pixmap.fill(self.color)
        self.line_color_select.setIcon(QIcon(self.line_color_pixmap))

        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self.ok_clicked)

        self.layout = QGridLayout()
        self.layout.addWidget(data_name_label, 1, 1)
        self.layout.addWidget(self.name_line_edit, 1, 2)
        self.layout.addWidget(color_select_label, 2, 1)
        self.layout.addWidget(self.line_color_select, 2, 2)
        self.layout.addWidget(self.ok_btn, 3, 2)

        self.setLayout(self.layout)

        self.ok_btn.setFocus()

    def select_color_clicked(self):
        self.color = self.color_dia.getColor(self.color)

        self.raise_()
        self.activateWindow()

        self.line_color_pixmap.fill(self.color)
        self.line_color_select.setIcon(QIcon(self.line_color_pixmap))

    def ok_clicked(self):
        self.done(QDialog.Accepted)

    def display(self):
        loop = QEventLoop()
        self.finished.connect(loop.quit)
        self.show()
        loop.exec()

        return self.name_line_edit.text(), self.color

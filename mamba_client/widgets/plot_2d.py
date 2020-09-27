import numpy as np

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QInputDialog, QGridLayout, QLabel,
                             QLineEdit, QPushButton, QColorDialog, QToolBar)
from PyQt5.QtCore import QSize, QEventLoop
from PyQt5.QtGui import QPixmap, QIcon, QColor

import pyqtgraph as pg

import mamba_client
from mamba_client.data_client import DataClientI


class Plot2DWidget(QWidget):
    def __init__(self, data_client: DataClientI):
        super().__init__()
        self.logger = mamba_client.logger
        self.data_client = data_client

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.navbar = QToolBar()
        self.navbar.setIconSize(QSize(15, 15))
        a = self.navbar.addAction(self._icon(':/icons/link.png'),
                                  "Select Data Source",
                                  self.show_data_select_dialog)
        self.layout.addWidget(self.navbar)

        # self.image_widget = pg.GraphicsLayoutWidget()
        # self.layout.addWidget(self.image_widget)

        # self.img_plot = pg.PlotItem()
        # self.image_widget.addItem(self.img_plot)
        # self.img = pg.ImageItem()
        # self.img_plot.addItem(self.img)
        #
        # self.img_plot.vb.setAspectLocked(True, 1)

        self.image_view = pg.ImageView()
        self.layout.addWidget(self.image_view)

        self.subscribed_data_name = ""
        self.registered_data_callbacks = []

    def show_data_select_dialog(self):
        name, ok = QInputDialog.getText(self, "Data source selection",
                                        "Data source:")

        if ok and name != self.subscribed_data_name:
            self.change_data_source(name)

    def change_data_source(self, data_name):
        for cbk in self.registered_data_callbacks:
            self.data_client.stop_requesting_data(cbk)

        cbk = self.update_data
        self.registered_data_callbacks.append(cbk)
        self.data_client.request_data(data_name, cbk)
        self.subscribed_data_name = data_name

    def update_data(self, _id, value, timestamp):
        if value is not None:
            shape = np.shape(value)
            if len(shape) != 2:
                self.logger.warning(f"Unsupported image shape {shape}.")
                return
            self.image_view.setImage(value)
            # levels = np.ptp(value)
            # if levels:
            #     self.img.updateImage(value, levels=levels)

    def __del__(self):
        for cbk in self.registered_data_callbacks:
            self.data_client.stop_requesting_data(cbk)

    @staticmethod
    def _icon(path):
        pm = QPixmap(path)
        return QIcon(pm)

    @classmethod
    def get_init_func(cls, data_client):
        return lambda: cls(data_client)



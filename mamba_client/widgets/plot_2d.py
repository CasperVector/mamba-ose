from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QInputDialog, QGridLayout, QLabel,
                             QLineEdit, QPushButton, QColorDialog, QToolBar)
from PyQt5.QtCore import QSize, QEventLoop
from PyQt5.QtGui import QPixmap, QIcon, QColor

import numpy as np
import pyqtgraph as pg

class Plot2DWidget(QWidget):
    def __init__(self, mnc):
        super().__init__()
        self.mnc = mnc

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
        self.mnc.subs["doc"].append(self.update_doc)

    def show_data_select_dialog(self):
        name, ok = QInputDialog.getText(self, "Data source selection",
                                        "Data source:")
        if ok and name != self.subscribed_data_name:
            self.subscribed_data_name = name

    def update_doc(self, msg):
        if msg["typ"][1] != "event":
            return
        value = msg["doc"]["data"].get(self.subscribed_data_name)
        if value is None:
            return
        shape = np.shape(value)
        if len(shape) != 2:
            return
        self.image_view.setImage(value)
        # levels = np.ptp(value)
        # if levels:
        #     self.img.updateImage(value, levels=levels)

    @staticmethod
    def _icon(path):
        pm = QPixmap(path)
        return QIcon(pm)


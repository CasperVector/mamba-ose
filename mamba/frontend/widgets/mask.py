from PyQt5.QtWidgets import QWidget, QPushButton
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QColor, QPainter, QFont, QFontMetrics
from PyQt5 import QtWidgets, QtCore, QtGui

# https://stackoverflow.com/questions/44264852/pyside-pyqt-overlay-widget
# Modified to have the ability to dynamically adapt to the text.
# TODO: fade-in and fade-out: https://stackoverflow.com/questions/48191399/pyqt-fading-a-qlabel

PADDING_LR = 80
PADDING_TB = 80


class MaskWidget(QWidget):
    closed = pyqtSignal()
    _close = pyqtSignal()

    def __init__(self, parent=None, text="", close_btn=True):
        super().__init__(parent)
        # make the window frameless
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.fillColor = QColor(30, 30, 30, 120)
        self.penColor = QColor("#333333")

        self.popup_fillColor = QColor(240, 240, 240, 255)
        self.popup_penColor = QColor(200, 200, 200, 255)

        self.close_btn_enable = close_btn
        self.close_btn = QPushButton(self)
        self.close_btn.setText("x")
        self.font = QFont()
        self.font.setPixelSize(18)
        self.font.setBold(True)
        self.font_metrics = QFontMetrics(self.font)
        self.close_btn.setFont(self.font)
        self.close_btn.setStyleSheet("background-color: rgba(0, 0, 0, 0)")
        self.close_btn.setFixedSize(30, 30)

        if close_btn:
            self.close_btn.setVisible(True)
            self.close_btn.clicked.connect(self._onclose)
        else:
            self.close_btn.setVisible(False)

        self._close.connect(self._onclose)

        self.setText(text)

    def setText(self, text):
        self.text = text
        lines = len(text.split("\n"))
        rect = self.font_metrics.boundingRect(text)
        self.t_width = rect.width()
        self.t_height = rect.height()*lines
        self.popup_width = self.t_width + 2*PADDING_LR
        self.popup_height = self.t_height + 2*PADDING_TB
        self.repaint()

    def closeBtnEnable(self, enable):
        if enable:
            self.close_btn.setVisible(True)
            self.close_btn.clicked.connect(self._onclose)
        else:

            self.close_btn.setVisible(False)
        self.repaint()

    def resizeEvent(self, event):
        s = self.size()
        ow = int(s.width() / 2 - self.popup_width / 2)
        oh = int(s.height() / 2 - self.popup_height / 2)
        self.close_btn.move(ow + self.popup_width - 35, oh + 5)

    def paintEvent(self, event):
        # This method is, in practice, drawing the contents of
        # your window.

        # get current window size
        s = self.size()
        qp = QPainter()
        qp.begin(self)
        qp.setRenderHint(QPainter.Antialiasing, True)
        qp.setPen(self.penColor)
        qp.setBrush(self.fillColor)
        qp.drawRect(0, 0, s.width(), s.height())

        # drawpopup
        qp.setPen(self.popup_penColor)
        qp.setBrush(self.popup_fillColor)
        ow = int(s.width()/2 - self.popup_width/2)
        oh = int(s.height()/2 - self.popup_height/2)
        qp.drawRoundedRect(ow, oh, self.popup_width, self.popup_height, 5, 5)

        qp.setFont(self.font)
        qp.setPen(QColor(70, 70, 70))
        qp.drawText(
            ow + PADDING_LR, oh + PADDING_TB,
            self.t_width, self.t_height,
            Qt.AlignCenter,
            self.text
        )

        qp.end()

    def _onclose(self):
        self.closed.emit()
        self.close()

    def safe_close(self):
        self._close.emit()

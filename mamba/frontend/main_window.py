from PyQt5.QtWidgets import QMainWindow, QWidget, QDockWidget
from PyQt5.QtCore import Qt, pyqtSignal
from .widgets.mask import MaskWidget


class MainWindow(QMainWindow):
    _show_popup_sig = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.widget_factory = {}
        self.docks = {}
        self.menus = {}

        self._popup = None
        self._show_popup_sig.connect(self._create_masked_popup)

        self.setWindowTitle("Mamba")
        self.setDockNestingEnabled(True)

    def add_widget(self, name, widget_init_func):
        self.widget_factory[name] = widget_init_func

    def set_layout(self, layout):
        # layout: { "top": [ widgets in this area ], ... }

        dock_area = {
            "top": Qt.TopDockWidgetArea,
            "bottom": Qt.BottomDockWidgetArea,
            "left": Qt.LeftDockWidgetArea,
            "right": Qt.RightDockWidgetArea
        }

        for area, widgets in layout:
            if area not in ["top", "bottom", "left", "right"]:
                raise ValueError("Unknown docking area.")

            if not isinstance(widgets, list):
                widgets = [widgets]

            last_widget = None

            for widget in widgets:
                if widget not in self.widget_factory:
                    raise ValueError("Unknown widget.")
                widget_inst = self.widget_factory[widget]()
                assert isinstance(widget_inst, QWidget)

                self.docks[widget] = QDockWidget(widget, self)
                self.docks[widget].setWidget(widget_inst)

                if not last_widget:
                    self.addDockWidget(dock_area[area], self.docks[widget])
                else:
                    self.splitDockWidget(last_widget, self.docks[widget],
                                         Qt.Horizontal)
                last_widget = self.docks[widget]

    def add_menu_item(self, menu, action):
        if menu not in self.menus:
            bar = self.menuBar()
            self.menus[menu] = bar.addMenu(menu)

        self.menus[menu].addAction(action)

    def show_masked_popup(self, text, closed_btn=True):
        if not self._popup:
            self._show_popup_sig.emit(text, closed_btn)
        else:
            self._popup.setText(text)
            self._popup.closeBtnEnable(closed_btn)

    def _create_masked_popup(self, text, closed_btn):
        self._popup = MaskWidget(self, text, closed_btn)
        self._popup.move(0, 0)
        self._popup.resize(self.width(), self.height())
        self._popup.show()
        self._popup.closed.connect(self._clear_masked_popup)

    def _clear_masked_popup(self):
        self._popup = None

    def close_masked_popup(self):
        if self._popup:
            self._popup.safe_close()
            self._popup = None

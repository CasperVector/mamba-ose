from PyQt5.QtWidgets import QMainWindow, QWidget, QDockWidget
from PyQt5.QtCore import Qt


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.widget_factory = {}
        self.docks = {}

        self.setDockNestingEnabled(True)

    def init_menubar(self):
        bar = self.menuBar()
        # TODO
        file = bar.addMenu("File")
        file.addAction("New")

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

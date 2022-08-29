from mamba.backend.zserver import ZError
from PyQt5.QtWidgets import (QDialog, QWidget, QFormLayout, QVBoxLayout,
    QLineEdit, QMessageBox, QPushButton, QTabWidget, QTableWidgetItem)

class MetadataGenerator(QDialog):
    def __init__(self, mrc, parent=None):
        super().__init__(parent)
        self.mrc = mrc
        self.widgets = {}
        self.set_ui()
        self.read()

    def set_ui(self):
        self.setWindowTitle("Metadata Generator")
        self.setFixedSize(720, 480)

        pane = QTabWidget()
        for name, fields in [
            ("Device Information", [
                ("sampleName", "Sample Name"),
                ("distance", "Distance"),
                ("energy", "Energy"),
                ("gap", "Gap")
            ]),
            ("Proposal Information", [
                ("proposalcode", "Proposal ID"),
                ("proposalname", "Proposal Name"),
                ("beamtimeId", "Beamtime ID"),
                ("startDate", "Start Date"),
                ("endDate", "Start Date")
            ])
        ]:
            layout = QFormLayout()
            for key, desc in fields:
                self.widgets[key] = QLineEdit(self)
                layout.addRow(desc, self.widgets[key])
            tab = QWidget()
            pane.addTab(tab, name)
            tab.setLayout(layout)

        submit_button = QPushButton("Submit")
        submit_button.clicked.connect(self.submit)
        layout = QVBoxLayout()
        layout.addWidget(pane)
        layout.addWidget(submit_button)
        self.setLayout(layout)

    def read(self):
        try:
            ret = self.mrc.req_rep("mdg/read")["ret"]
        except ZError as e:
            return QMessageBox.warning(self, "Error", str(e))
        for k, v in ret.items():
            w = self.widgets.get(k)
            if w:
                w.setText(v)

    def submit(self):
        try:
            self.mrc.do_cmd("U.mdg.set(%r)\n" %
                {k: v.text() for k, v in self.widgets.items()})
        except ZError as e:
            return QMessageBox.warning(self, "Error", str(e))


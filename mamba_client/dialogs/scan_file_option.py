from PyQt5.QtWidgets import QDialog, QTableWidgetItem
from PyQt5.QtCore import Qt, QEventLoop

from mamba_client.widgets.ui.ui_scanfileoption import Ui_ScanFileOption


DATA_DEV_COL = 0
DATA_NAME_COL = 1
DATA_TYPE_COL = 2
DATA_SAVE_COL = 3
DATA_SINGLE_COL = 4


class ScanFileOptionDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.ui = Ui_ScanFileOption()
        self.ui.setupUi(self)

        self.ui.scanDatasetTable.setHorizontalHeaderItem(
            DATA_DEV_COL, QTableWidgetItem("Dev"))
        self.ui.scanDatasetTable.setHorizontalHeaderItem(
            DATA_NAME_COL, QTableWidgetItem("Name"))
        self.ui.scanDatasetTable.setHorizontalHeaderItem(
            DATA_TYPE_COL, QTableWidgetItem("Type"))
        self.ui.scanDatasetTable.setHorizontalHeaderItem(
            DATA_SAVE_COL, QTableWidgetItem("Save?"))
        self.ui.scanDatasetTable.setHorizontalHeaderItem(
            DATA_SINGLE_COL, QTableWidgetItem("Single File?"))

        self.ui.cancelBtn.setFocusPolicy(Qt.NoFocus)
        self.ui.cancelBtn.clicked.connect(self.reject)

        self.ui.okBtn.setFocusPolicy(Qt.NoFocus)
        self.ui.okBtn.clicked.connect(self.accept)

    def populate_scan_dataset(self, data_options):
        self.ui.scanDatasetTable.blockSignals(True)
        self.config_widget.setRowCount(len(data_options))
        for i, data_option in enumerate(data_options):
            dev_item = self._get_table_uneditable_item(data_option['dev'])
            name_item = self._get_table_uneditable_item(data_option['name'])
            type_item = self._get_table_uneditable_item(str(data_option['type']))
            save_item = self._get_table_checkbox_item(data_option['save'])
            single_item = self._get_table_checkbox_item(data_option['single'])
            self.ui.scanDatasetTable.setItem(i, DATA_DEV_COL, dev_item)
            self.ui.scanDatasetTable.setItem(i, DATA_NAME_COL, name_item)
            self.ui.scanDatasetTable.setItem(i, DATA_TYPE_COL, type_item)
            self.ui.scanDatasetTable.setItem(i, DATA_SAVE_COL, save_item)
            self.ui.scanDatasetTable.setItem(i, DATA_SINGLE_COL, single_item)

        self.ui.scanDatasetTable.blockSignals(False)

    def dump_data_options(self):
        data_options = []
        for i in range(self.ui.scanDatasetTable.rowCount()):
            data_option = {
                'dev': self.ui.scanDatasetTable.item(i, DATA_DEV_COL).text(),
                'name': self.ui.scanDatasetTable.item(i, DATA_NAME_COL).text(),
                'save': self._get_table_item_checked(self.ui.scanDatasetTable, i, DATA_SAVE_COL),
                'single': self._get_table_item_checked(self.ui.scanDatasetTable, i, DATA_SINGLE_COL)
            }
            data_options.append(data_option)

        return data_options

    def display(self, data_options):
        loop = QEventLoop()
        self.finished.connect(loop.quit)
        self.populate_scan_dataset(data_options)
        self.show()
        loop.exec()

        return self.dump_data_options()

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

    @staticmethod
    def _get_table_item_checked(table, row, col):
        return table.item(row, col).checkState() == Qt.Checked

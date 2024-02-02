from mamba.backend.zserver import ZError, zsv_err_fmt
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpacerItem)

class LoginDialog(QDialog):
    def __init__(self, mrc, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login Window")
        self.mrc = mrc

        txt1 = QLabel()
        txt1.setText("Please enter your information:")
        self.login_username = QLineEdit(self)
        self.login_pwd = QLineEdit(self)
        self.login_pwd.setEchoMode(QLineEdit.Password)
        submit_button = QPushButton("Login")
        submit_button.clicked.connect(self.check_login)

        layout = QFormLayout()
        layout.addWidget(txt1)
        layout.addRow("Username:", self.login_username)
        layout.addRow("Password:", self.login_pwd)
        layout.addWidget(submit_button)
        self.setLayout(layout)

    def check_login(self):
        self.mrc.req_rep("auth/pw", pw = self.login_pwd.text())
        try:
            self.mrc.do_cmd("U.auth.login(%r)\n" % self.login_username.text())
        except ZError as e:
            return QMessageBox.warning(self, "Error", zsv_err_fmt(e))
        return QMessageBox.about(self, "Success", "Logged in.")

class LogoutDialog(QDialog):
    def __init__(self, mrc, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Logout Window")
        self.mrc = mrc

        txt1 = QLabel()
        txt1.setText("Really logout?")
        submit_button = QPushButton("Logout")
        submit_button.clicked.connect(self.check_logout)

        layout = QFormLayout()
        layout.addWidget(txt1)
        layout.addWidget(submit_button)
        self.setLayout(layout)

    def check_logout(self):
        try:
            self.mrc.do_cmd("U.auth.logout()\n")
        except ZError as e:
            return QMessageBox.warning(self, "Error", zsv_err_fmt(e))
        return QMessageBox.about(self, "Success", "Logged out.")


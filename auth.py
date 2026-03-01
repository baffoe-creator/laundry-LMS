#!/usr/bin/env python3
"""
auth.py

PyQt5-based Login window for the Laundry Management System (LMS).

- Uses models.authenticate_user to verify credentials.
- On successful login, opens the Dashboard window (dashboard.DashboardWindow)
  and closes the login window.
- Passwords are verified using PBKDF2 via database.verify_password (wired through models).

Run:
    python auth.py

Notes:
- This is a minimal, practical login UI targeted at non-technical staff (large input fields).
- For production consider adding lockout after repeated failures and logging.
"""

import sys
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QMessageBox,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

import models

from dashboard import DashboardWindow


class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LMS — Login")
        self.setMinimumSize(400, 220)
        self.setup_ui()

    def setup_ui(self):
        # Use larger font sizes for readability in a shop environment
        label_font = QFont("Segoe UI", 10)
        input_font = QFont("Segoe UI", 11)

        v = QVBoxLayout()
        v.setSpacing(12)
        v.setContentsMargins(24, 24, 24, 24)

        title = QLabel("Laundry Management System — Login")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        v.addWidget(title)

        # Username
        usr_layout = QVBoxLayout()
        usr_lbl = QLabel("Username")
        usr_lbl.setFont(label_font)
        self.usr_input = QLineEdit()
        self.usr_input.setFont(input_font)
        self.usr_input.setPlaceholderText("Enter username")
        usr_layout.addWidget(usr_lbl)
        usr_layout.addWidget(self.usr_input)
        v.addLayout(usr_layout)

        # Password
        pwd_layout = QVBoxLayout()
        pwd_lbl = QLabel("Password")
        pwd_lbl.setFont(label_font)
        self.pwd_input = QLineEdit()
        self.pwd_input.setFont(input_font)
        self.pwd_input.setEchoMode(QLineEdit.Password)
        self.pwd_input.setPlaceholderText("Enter password")
        pwd_layout.addWidget(pwd_lbl)
        pwd_layout.addWidget(self.pwd_input)
        v.addLayout(pwd_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch(1)
        self.login_btn = QPushButton("Login")
        self.login_btn.setFont(QFont("Segoe UI", 10))
        self.login_btn.clicked.connect(self.attempt_login)
        btn_layout.addWidget(self.login_btn)

        self.quit_btn = QPushButton("Quit")
        self.quit_btn.setFont(QFont("Segoe UI", 10))
        self.quit_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.quit_btn)

        v.addLayout(btn_layout)

        # Helpful hint
        hint = QLabel("Tip: default admin / admin123 (change password after first login)")
        hint.setFont(QFont("Segoe UI", 9))
        hint.setAlignment(Qt.AlignCenter)
        v.addWidget(hint)

        self.setLayout(v)

        # Connect Enter key on password to login
        self.pwd_input.returnPressed.connect(self.attempt_login)

    def attempt_login(self):
        username = self.usr_input.text().strip()
        password = self.pwd_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Missing credentials", "Please enter username and password.")
            return

        user = models.authenticate_user(username, password)
        if user:
            # Successful login: open dashboard and pass user info
            self.open_dashboard(user)
        else:
            QMessageBox.critical(self, "Login failed", "Invalid username or password.")
            # Optionally clear password field for security
            self.pwd_input.clear()
            self.pwd_input.setFocus()

    def open_dashboard(self, user_info: dict):
        # Hide login window (we'll close it after dashboard opens)
        self.hide()
        self.dashboard = DashboardWindow(current_user=user_info)
        # Connect dashboard logout signal to show login again (dashboard will call .close on logout)
        self.dashboard.show()
        self.dashboard.on_logout = self.handle_logout  # simple callback

    def handle_logout(self):
        # When dashboard signals logout, show login window again
        self.usr_input.clear()
        self.pwd_input.clear()
        self.show()
        self.usr_input.setFocus()


def main():
    app = QApplication(sys.argv)
    login = LoginWindow()
    login.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
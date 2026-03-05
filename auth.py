#!/usr/bin/env python3
"""
auth.py

Authentication and main entry point for LMS.

Handles login dialog, user session, and launching the dashboard.
Updated to load style.qss stylesheet with fallback and PyInstaller support.
"""

import sys
import os
from typing import Optional, Dict, Any
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QComboBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

import models
import database


def get_stylesheet_path() -> str:
    """
    Get the correct path to style.qss when running from source or frozen exe.
    Checks sys._MEIPASS first for PyInstaller bundles, then falls back to local path.
    """
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        candidate = os.path.join(sys._MEIPASS, 'style.qss')
        if os.path.exists(candidate):
            return candidate
    
    # Fall back to local directory
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'style.qss')


def load_stylesheet(app: QApplication) -> None:
    """
    Load and apply the QSS stylesheet if available.
    Graceful fallback if file not found.
    """
    style_path = get_stylesheet_path()
    try:
        with open(style_path, 'r', encoding='utf-8') as f:
            stylesheet = f.read()
            app.setStyleSheet(stylesheet)
            print(f"Stylesheet loaded from: {style_path}")
    except FileNotFoundError:
        print(f"Stylesheet not found at {style_path}, using default styling.")
    except Exception as e:
        print(f"Error loading stylesheet: {e}")


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LMS — Login")
        self.setFixedSize(360, 200)  # Reduced height since we removed the role selector
        self.user = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()

        # Logo / Title
        title = QLabel("Laundry Management System")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont("Segoe UI", 14, QFont.Bold)
        title.setFont(title_font)
        layout.addWidget(title)

        # Form
        form_layout = QVBoxLayout()
        form_layout.setSpacing(12)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Username")
        self.username_edit.setMinimumHeight(36)
        form_layout.addWidget(self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Password")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setMinimumHeight(36)
        form_layout.addWidget(self.password_edit)

        layout.addLayout(form_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self.authenticate)
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.setProperty("accent", True)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        
        btn_layout.addWidget(self.login_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        # Version info
        version = QLabel("v1.0.0")
        version.setAlignment(Qt.AlignRight)
        version.setStyleSheet("color: #6B7C8D; font-size: 8pt;")
        layout.addWidget(version)

        self.setLayout(layout)

    def authenticate(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        
        if not username or not password:
            QMessageBox.warning(self, "Missing fields", "Please enter username and password.")
            return

        # Try database authentication
        user = models.authenticate_user(username, password)
        if user:
            self.user = user
            self.accept()
        else:
            QMessageBox.warning(self, "Login failed", "Invalid username or password.")


def main():
    app = QApplication(sys.argv)
    
    # Load stylesheet
    load_stylesheet(app)
    
    # Initialize database if needed
    db_path = database.get_db_path()
    if not os.path.exists(db_path):
        database.init_db()
        database.seed_admin()
        database.seed_price_catalogue()
        database.migrate_ledger_from_existing_data()
    
    # Show login
    login = LoginDialog()
    if login.exec_() == QDialog.Accepted:
        from dashboard import DashboardWindow
        dashboard = DashboardWindow(current_user=login.user)
        dashboard.show()
        sys.exit(app.exec_())
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
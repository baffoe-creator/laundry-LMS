#!/usr/bin/env python3
"""
settings.py

Simple settings persistence for the Laundry Management System (LMS).

- Persists a JSON config file (config.json) in the project root.
- Provides helper functions:
    - load_settings() -> dict
    - save_settings(data: dict)
    - get_company_info() -> dict
- Also provides a PyQt5 SettingsWindow to edit company info (name, address, phone, email, logo path)
  and save it to config.json.

Note: Keep this file small and dependency-free (uses only stdlib + PyQt5 for the UI).
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
import os

# Config filename in project root
CONFIG_PATH = Path("config.json")

# Default settings structure
DEFAULT_SETTINGS = {
    "company": {
        "name": "NII ET AL Laundry",
        "address": "123 Laundry Lane\nCity, Country",
        "phone": "0700-000-000",
        "email": "info@niietallaundry.example",
        # optional logo_path (relative or absolute)
        "logo_path": ""
    }
}


def load_settings() -> Dict[str, Any]:
    """Load settings from config.json; return DEFAULT_SETTINGS when file missing or invalid."""
    if not CONFIG_PATH.exists():
        return DEFAULT_SETTINGS.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # ensure expected keys
            if "company" not in data:
                data["company"] = DEFAULT_SETTINGS["company"].copy()
            return data
    except Exception:
        return DEFAULT_SETTINGS.copy()


def save_settings(data: Dict[str, Any]) -> None:
    """Save settings to config.json (creates/overwrites)."""
    # ensure directory exists
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_company_info() -> Dict[str, str]:
    """Convenience: return the 'company' dict (with defaults)."""
    settings = load_settings()
    return settings.get("company", DEFAULT_SETTINGS["company"].copy())


# -------------------------
# Settings UI (PyQt5)
# -------------------------
# The UI is optional for headless use, but convenient inside the Dashboard.
try:
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QLineEdit, QTextEdit, QPushButton, QFormLayout, QHBoxLayout,
        QVBoxLayout, QFileDialog, QMessageBox, QApplication
    )
    from PyQt5.QtGui import QFont
    from PyQt5.QtCore import Qt
except Exception:
    # If PyQt5 not available at import time, the module still functions for read/write.
    QWidget = None  # type: ignore

class SettingsWindow(QWidget):
    """
    Simple window to edit company information and save to config.json.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LMS — Settings")
        self.setMinimumSize(600, 420)
        self._build_ui()
        self.load_into_ui()

    def _build_ui(self):
        font_input = QFont("Segoe UI", 10)

        form_layout = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setFont(font_input)
        form_layout.addRow("Company Name:", self.name_input)

        self.address_input = QTextEdit()
        self.address_input.setFont(font_input)
        self.address_input.setPlaceholderText("Address (multi-line)")
        self.address_input.setFixedHeight(100)
        form_layout.addRow("Address:", self.address_input)

        self.phone_input = QLineEdit()
        self.phone_input.setFont(font_input)
        form_layout.addRow("Phone:", self.phone_input)

        self.email_input = QLineEdit()
        self.email_input.setFont(font_input)
        form_layout.addRow("Email:", self.email_input)

        # Logo path + browse button
        logo_layout = QHBoxLayout()
        self.logo_input = QLineEdit()
        self.logo_input.setFont(font_input)
        self.logo_input.setPlaceholderText("Path to logo image (optional)")
        logo_layout.addWidget(self.logo_input)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_logo)
        logo_layout.addWidget(browse_btn)
        form_layout.addRow("Logo:", logo_layout)

        # Save / Cancel
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self.save_clicked)
        btn_layout.addWidget(save_btn)
        cancel_btn = QPushButton("Close")
        cancel_btn.clicked.connect(self.close)
        btn_layout.addWidget(cancel_btn)

        v = QVBoxLayout()
        v.addLayout(form_layout)
        v.addStretch(1)
        v.addLayout(btn_layout)
        self.setLayout(v)

    def load_into_ui(self):
        info = get_company_info()
        self.name_input.setText(info.get("name", ""))
        self.address_input.setPlainText(info.get("address", ""))
        self.phone_input.setText(info.get("phone", ""))
        self.email_input.setText(info.get("email", ""))
        self.logo_input.setText(info.get("logo_path", ""))

    def browse_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Logo Image", str(Path.cwd()), "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.logo_input.setText(path)

    def save_clicked(self):
        company = {
            "name": self.name_input.text().strip() or DEFAULT_SETTINGS["company"]["name"],
            "address": self.address_input.toPlainText().strip() or DEFAULT_SETTINGS["company"]["address"],
            "phone": self.phone_input.text().strip() or DEFAULT_SETTINGS["company"]["phone"],
            "email": self.email_input.text().strip() or DEFAULT_SETTINGS["company"]["email"],
            "logo_path": self.logo_input.text().strip() or ""
        }
        data = {"company": company}
        try:
            save_settings(data)
            QMessageBox.information(self, "Saved", "Settings saved to config.json")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"Failed to save settings: {e}")
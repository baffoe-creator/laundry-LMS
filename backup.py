#!/usr/bin/env python3
"""
backup.py

Simple Backup and Restore UI for the Laundry Management System (LMS).

Features:
- Create a timestamped backup copy of the SQLite DB (default lms.db) into ./backups/
- Restore from an existing SQLite file (selected via file dialog) after confirmation
- Basic safety checks (file exists, basic SQLite header check)
- Provides small CLI functions for scripting the same functionality:
    backup_database(dest_dir=None) -> path_to_backup
    restore_database(src_path, dest_path=None) -> dest_path

Usage (GUI):
    python backup.py

Usage (CLI from other scripts):
    from backup import backup_database, restore_database

Notes:
- Restoring replaces the current DB file (get_db_path()). The UI asks for confirmation.
- For scheduled automated backups, call backup_database() from a scheduled task.
"""

import os
import shutil
from pathlib import Path
import datetime
import sys

# PyQt5 UI imports
try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox, QApplication
    )
    from PyQt5.QtGui import QFont
except Exception:
    QWidget = None  # type: ignore

import database


BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _is_sqlite_file(path: Path) -> bool:
    """Quick check: valid SQLite files start with 'SQLite format 3' in first 16 bytes."""
    try:
        with open(path, "rb") as f:
            header = f.read(16)
            return header.startswith(b"SQLite format 3")
    except Exception:
        return False


def backup_database(dest_dir: str | None = None) -> str:
    """
    Create a timestamped backup copy of the database.
    Returns the path to the backup file.
    """
    src = Path(database.get_db_path())
    if not src.exists():
        raise FileNotFoundError(f"Database file not found: {src}")

    if dest_dir:
        dest_folder = Path(dest_dir)
    else:
        dest_folder = BACKUP_DIR
    dest_folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_name = f"lms_backup_{timestamp}.db"
    dest_path = dest_folder / dest_name

    shutil.copy2(src, dest_path)
    return str(dest_path.resolve())


def restore_database(src_path: str, dest_path: str | None = None, create_backup: bool = True) -> str:
    """
    Restore database from src_path into the application's DB file (or dest_path if provided).
    If create_backup is True, create a backup of the current DB before overwriting.
    Returns the path to the restored DB (destination).
    """
    src = Path(src_path)
    if not src.exists():
        raise FileNotFoundError("Source file not found: " + str(src))

    if not _is_sqlite_file(src):
        raise ValueError("Source file does not appear to be a valid SQLite database.")

    dst = Path(dest_path) if dest_path else Path(database.get_db_path())
    if dst.exists() and create_backup:
        # Create a backup of current DB first
        backup_database()

    # Overwrite destination
    shutil.copy2(src, dst)
    return str(dst.resolve())


# --- Simple PyQt5 GUI for backup/restore ---
class BackupWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LMS — Backup & Restore")
        self.setMinimumSize(480, 200)
        self._build_ui()

    def _build_ui(self):
        font = QFont("Segoe UI", 10)
        layout = QVBoxLayout()
        info = QLabel("Create a backup of the current database or restore from an existing .db file.")
        info.setWordWrap(True)
        info.setFont(font)
        layout.addWidget(info)

        self.backup_btn = QPushButton("Create Backup Now")
        self.backup_btn.clicked.connect(self.create_backup)
        layout.addWidget(self.backup_btn)

        self.restore_btn = QPushButton("Restore From File")
        self.restore_btn.clicked.connect(self.restore_from_file)
        layout.addWidget(self.restore_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)

        self.setLayout(layout)

    def create_backup(self):
        try:
            out = backup_database()
            QMessageBox.information(self, "Backup created", f"Backup saved to:\n{out}")
        except Exception as e:
            QMessageBox.critical(self, "Backup failed", f"Failed to create backup: {e}")

    def restore_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select database file to restore", str(Path.cwd()), "SQLite DB Files (*.db *.sqlite *.sqlite3);;All files (*)")
        if not path:
            return
        confirm = QMessageBox.question(self, "Confirm restore", f"Restore database from:\n{path}\n\nThis will replace the current database and cannot be undone (a backup will be created first). Continue?", QMessageBox.Yes | QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        try:
            restored = restore_database(path)
            QMessageBox.information(self, "Restore complete", f"Database restored from:\n{path}\n\nCurrent database now at:\n{restored}")
        except Exception as e:
            QMessageBox.critical(self, "Restore failed", f"Failed to restore database: {e}")


if __name__ == "__main__":
    if QWidget is None:
        print("PyQt5 is required to run the GUI. You can still use backup_database() and restore_database() functions programmatically.")
        raise SystemExit(1)
    app = QApplication(sys.argv)
    w = BackupWindow()
    w.show()
    sys.exit(app.exec_())
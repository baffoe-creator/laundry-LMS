#!/usr/bin/env python3
"""
users.py

Users Management UI for the Laundry Management System (LMS).

Features:
- List existing users
- Create new user (username, password, role)
- Change user's role (admin/manager/cashier)
- Reset user's password (sets a new password using PBKDF2 hash)
- Delete user (with safeguards to prevent deleting the last admin)

This UI is intended for admin/manager use. It uses database.connect_db and
database.hash_password for secure password handling.

Usage:
    python users.py

Important:
- The default admin (seeded by database.py) should remain; UI prevents deleting the last admin.
"""

import sys
from typing import Optional, Dict, Any, List
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QFormLayout, QLineEdit, QMessageBox, QComboBox, QInputDialog
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

import database


def list_users_from_db() -> List[Dict[str, Any]]:
    """
    Return list of users (user_id, username, role, created_at)
    """
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, role, created_at FROM users ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def count_admins() -> int:
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM users WHERE role = 'admin'")
    r = cur.fetchone()
    conn.close()
    return int(r["cnt"] or 0)


class UsersWindow(QWidget):
    def __init__(self, current_user: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.current_user = current_user or database.get_user_by_username("admin")
        if not self.current_user:
            raise RuntimeError("No current user")
        self.setWindowTitle("LMS — User Management")
        self.setMinimumSize(800, 520)
        self._build_ui()
        self.load_users()

    def _build_ui(self):
        font = QFont("Segoe UI", 10)
        main = QHBoxLayout()

        # Left: user list
        left = QVBoxLayout()
        self.users_list = QListWidget()
        self.users_list.setFont(font)
        self.users_list.itemClicked.connect(self.on_user_selected)
        left.addWidget(QLabel("Users"))
        left.addWidget(self.users_list)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_users)
        left.addWidget(refresh_btn)
        main.addLayout(left, stretch=3)

        # Right: actions and forms
        right = QVBoxLayout()

        # Create user
        create_group = QFormLayout()
        self.new_username = QLineEdit()
        self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.Password)
        self.new_role = QComboBox()
        self.new_role.addItems(["cashier", "manager", "admin"])
        create_btn = QPushButton("Create User")
        create_btn.clicked.connect(self.create_user_clicked)
        create_group.addRow("Username:", self.new_username)
        create_group.addRow("Password:", self.new_password)
        create_group.addRow("Role:", self.new_role)
        create_group.addRow("", create_btn)
        right.addLayout(create_group)

        # Selected user details and management
        self.sel_label = QLabel("Select a user to manage")
        right.addWidget(self.sel_label)

        manage_group = QFormLayout()
        self.sel_username = QLabel("-")
        self.sel_role = QComboBox()
        self.sel_role.addItems(["cashier", "manager", "admin"])
        update_role_btn = QPushButton("Update Role")
        update_role_btn.clicked.connect(self.update_role_clicked)
        manage_group.addRow("Username:", self.sel_username)
        manage_group.addRow("Role:", self.sel_role)
        manage_group.addRow("", update_role_btn)

        reset_pw_btn = QPushButton("Reset Password")
        reset_pw_btn.clicked.connect(self.reset_password_clicked)
        manage_group.addRow("", reset_pw_btn)

        delete_btn = QPushButton("Delete User")
        delete_btn.clicked.connect(self.delete_user_clicked)
        manage_group.addRow("", delete_btn)

        right.addLayout(manage_group)
        right.addStretch(1)

        main.addLayout(right, stretch=4)
        self.setLayout(main)

    def load_users(self):
        self.users_list.clear()
        rows = list_users_from_db()
        for r in rows:
            item = QListWidgetItem(f"{r['user_id']} - {r['username']} ({r['role']})")
            item.setData(Qt.UserRole, r)
            self.users_list.addItem(item)

    def on_user_selected(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        self.selected_user = data
        self.sel_label.setText(f"Selected user_id={data['user_id']}")
        self.sel_username.setText(data["username"])
        # set role combobox to current role
        idx = self.sel_role.findText(data["role"])
        if idx >= 0:
            self.sel_role.setCurrentIndex(idx)

    def create_user_clicked(self):
        username = self.new_username.text().strip()
        password = self.new_password.text().strip()
        role = self.new_role.currentText()
        if not username or not password:
            QMessageBox.warning(self, "Missing fields", "Provide username and password.")
            return
        try:
            # Use database.hash_password and direct insert to avoid double-hash
            ph = database.hash_password(password)
            conn = database.connect_db()
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", (username, ph, role))
            conn.commit()
            conn.close()
            QMessageBox.information(self, "User created", f"User '{username}' created.")
            self.new_username.clear()
            self.new_password.clear()
            self.load_users()
        except Exception as e:
            QMessageBox.critical(self, "Create failed", f"Failed to create user: {e}")

    def update_role_clicked(self):
        if not getattr(self, "selected_user", None):
            QMessageBox.warning(self, "No user selected", "Select a user to update their role.")
            return
        uid = int(self.selected_user["user_id"])
        new_role = self.sel_role.currentText()
        try:
            conn = database.connect_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET role = ? WHERE user_id = ?", (new_role, uid))
            conn.commit()
            conn.close()
            QMessageBox.information(self, "Role updated", f"User {self.selected_user['username']} role updated to {new_role}.")
            self.load_users()
        except Exception as e:
            QMessageBox.critical(self, "Update failed", f"Failed to update role: {e}")

    def reset_password_clicked(self):
        if not getattr(self, "selected_user", None):
            QMessageBox.warning(self, "No user selected", "Select a user to reset password.")
            return
        uid = int(self.selected_user["user_id"])
        username = self.selected_user["username"]
        # Ask for new password (simple prompt)
        new_pw, ok = QInputDialog.getText(self, "Reset Password", f"Enter new password for {username}:", QLineEdit.Password)
        if not ok or not new_pw:
            return
        try:
            ph = database.hash_password(new_pw)
            conn = database.connect_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (ph, uid))
            conn.commit()
            conn.close()
            QMessageBox.information(self, "Password reset", f"Password for {username} was updated.")
        except Exception as e:
            QMessageBox.critical(self, "Reset failed", f"Failed to reset password: {e}")

    def delete_user_clicked(self):
        if not getattr(self, "selected_user", None):
            QMessageBox.warning(self, "No user selected", "Select a user to delete.")
            return
        uid = int(self.selected_user["user_id"])
        username = self.selected_user["username"]
        # Prevent deleting self
        if uid == int(self.current_user["user_id"]):
            QMessageBox.warning(self, "Cannot delete self", "You cannot delete the currently logged-in user.")
            return
        # Prevent deleting last admin
        if self.selected_user["role"] == "admin" and count_admins() <= 1:
            QMessageBox.warning(self, "Protected", "Cannot delete the last admin user.")
            return
        confirm = QMessageBox.question(self, "Confirm delete", f"Delete user {username} (id={uid})?", QMessageBox.Yes | QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        try:
            conn = database.connect_db()
            cur = conn.cursor()
            cur.execute("DELETE FROM users WHERE user_id = ?", (uid,))
            conn.commit()
            conn.close()
            QMessageBox.information(self, "Deleted", f"User {username} deleted.")
            self.load_users()
            # Clear selection
            self.sel_label.setText("Select a user to manage")
            self.sel_username.setText("-")
        except Exception as e:
            QMessageBox.critical(self, "Delete failed", f"Failed to delete user: {e}")


if __name__ == "__main__":
    # Simple runner
    app = QApplication(sys.argv)
    admin = database.get_user_by_username("admin")
    w = UsersWindow(current_user=admin)
    w.show()
    sys.exit(app.exec_())
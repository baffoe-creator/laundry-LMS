#!/usr/bin/env python3
"""
customers.py

Customers UI widget for LMS.

Robust handling:
- Accepts rows returned as sqlite3.Row or dict
- Uses models.find_customers if available, otherwise falls back to direct DB query
"""
from typing import Optional, Dict, Any, List
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton, QListWidget,
    QListWidgetItem, QLabel, QTextEdit, QMessageBox, QGroupBox
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

import sqlite3
import models
import database

def _to_dict_row(r):
    """Convert sqlite3.Row or dict-like to a plain dict safely."""
    if r is None:
        return {}
    # sqlite3.Row is mapping but doesn't implement get; convert to dict
    try:
        if isinstance(r, sqlite3.Row):
            return dict(r)
    except Exception:
        pass
    # if it's already a dict-like, try dict()
    try:
        return dict(r)
    except Exception:
        # fallback to attribute access
        out = {}
        try:
            out['customer_id'] = r['customer_id']
            out['name'] = r.get('name') if hasattr(r, 'get') else r['name']
            out['phone'] = r.get('phone') if hasattr(r, 'get') else r['phone']
        except Exception:
            pass
        return out

def fmt_customer_line(c: Dict[str, Any]) -> str:
    """Format a single customer record for display (works with sqlite3.Row or dict)."""
    d = _to_dict_row(c)
    cid = d.get('customer_id') or d.get('customer_id') == 0 and 0
    name = d.get('name') or ""
    phone = d.get('phone') or ""
    return f"{cid} - {name} ({phone})"

class CustomersWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customers")
        self._build_ui()
        self.load_recent_customers()

    def _build_ui(self):
        font = QFont("Segoe UI", 10)
        main = QVBoxLayout()

        # Search group
        search_group = QGroupBox("Search Customers")
        s_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name or phone")
        self.search_input.setFont(font)
        s_layout.addWidget(self.search_input)
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.do_search)
        s_layout.addWidget(self.search_btn)
        search_group.setLayout(s_layout)
        main.addWidget(search_group)

        # Results list
        self.results_list = QListWidget()
        self.results_list.setFont(font)
        self.results_list.itemClicked.connect(self.on_result_selected)
        main.addWidget(self.results_list, stretch=2)

        # Create customer group
        create_group = QGroupBox("Create Customer")
        cf = QFormLayout()
        self.name_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.notes_input = QTextEdit()
        self.notes_input.setFixedHeight(80)
        cf.addRow("Name:", self.name_input)
        cf.addRow("Phone:", self.phone_input)
        cf.addRow("Notes (optional):", self.notes_input)
        create_btn = QPushButton("Create Customer")
        create_btn.clicked.connect(self.create_customer)
        cf.addRow("", create_btn)
        create_group.setLayout(cf)
        main.addWidget(create_group)

        # Selected customer display
        self.selected_label = QLabel("No customer selected")
        self.selected_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        main.addWidget(self.selected_label)

        self.setLayout(main)

    def load_recent_customers(self, limit: int = 50):
        """
        Load recent customers via DB query.
        """
        try:
            conn = database.connect_db()
            cur = conn.cursor()
            cur.execute("SELECT customer_id, name, phone, created_at FROM customers ORDER BY created_at DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Failed to load customers: {e}")
            return

        self.results_list.clear()
        for r in rows:
            d = _to_dict_row(r)
            item = QListWidgetItem(fmt_customer_line(d))
            item.setData(Qt.UserRole, d)
            self.results_list.addItem(item)

    def do_search(self):
        q = self.search_input.text().strip()
        if not q:
            QMessageBox.information(self, "Empty search", "Enter a name or phone to search.")
            return

        # Prefer models.find_customers if available
        results = None
        try:
            if hasattr(models, "find_customers"):
                results = models.find_customers(q)
        except Exception:
            results = None

        if results is None:
            # fallback to DB LIKE query
            try:
                conn = database.connect_db()
                cur = conn.cursor()
                like = f"%{q}%"
                cur.execute("SELECT customer_id, name, phone, created_at FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY created_at DESC LIMIT 200", (like, like))
                rows = cur.fetchall()
                conn.close()
                results = rows
            except Exception as e:
                QMessageBox.critical(self, "Search failed", f"Search error: {e}")
                return

        self.results_list.clear()
        if not results:
            QMessageBox.information(self, "No results", "No customers found.")
            return
        for r in results:
            d = _to_dict_row(r)
            item = QListWidgetItem(fmt_customer_line(d))
            item.setData(Qt.UserRole, d)
            self.results_list.addItem(item)

    def create_customer(self):
        name = self.name_input.text().strip()
        phone = self.phone_input.text().strip() or None
        # notes not persisted by default; keep if DB supports
        if not name:
            QMessageBox.warning(self, "Missing name", "Please enter customer name.")
            return
        try:
            cid = models.create_customer(name, phone)
        except Exception as e:
            QMessageBox.critical(self, "Create failed", f"Failed to create customer: {e}")
            return
        QMessageBox.information(self, "Customer created", f"Customer created with id {cid}.")
        self.name_input.clear()
        self.phone_input.clear()
        self.notes_input.clear()
        # refresh list and auto-select newly created
        self.load_recent_customers()
        # find and select new item
        items = self.results_list.findItems(f"{cid} -", Qt.MatchStartsWith)
        if items:
            self.results_list.setCurrentItem(items[0])
            self.on_result_selected(items[0])

    def on_result_selected(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        if not data:
            return
        d = _to_dict_row(data)
        self.selected_label.setText(fmt_customer_line(d))
        self.selected_customer = d

if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = CustomersWidget()
    w.show()
    sys.exit(app.exec_())
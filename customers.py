#!/usr/bin/env python3
"""
customers.py

Customers UI widget for LMS.

Updated with:
- Order history panel showing customer's orders (Change 1)
- Customer type field in create form (Change 2e)
- Outstanding balance summary line (Feature 1f)
"""
from typing import Optional, Dict, Any, List
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton, QListWidget,
    QListWidgetItem, QLabel, QTextEdit, QMessageBox, QGroupBox, QTableWidget, 
    QTableWidgetItem, QHeaderView, QComboBox
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

import sqlite3
import models
import database

def _to_dict_row(r):
    """Convert sqlite3.Row or dict-like to a plain dict safely."""
    if r is None:
        return {}
    try:
        if isinstance(r, sqlite3.Row):
            return dict(r)
    except Exception:
        pass
    try:
        return dict(r)
    except Exception:
        out = {}
        try:
            out['customer_id'] = r['customer_id']
            out['name'] = r.get('name') if hasattr(r, 'get') else r['name']
            out['phone'] = r.get('phone') if hasattr(r, 'get') else r['phone']
            out['customer_type'] = r.get('customer_type') if hasattr(r, 'get') else r.get('customer_type', 'individual')
        except Exception:
            pass
        return out

def fmt_customer_line(c: Dict[str, Any]) -> str:
    """Format a single customer record for display."""
    d = _to_dict_row(c)
    cid = d.get('customer_id') or d.get('customer_id') == 0 and 0
    name = d.get('name') or ""
    phone = d.get('phone') or ""
    cust_type = d.get('customer_type') or "individual"
    return f"{cid} - {name} ({phone}) [{cust_type}]"

class CustomersWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customers")
        self.selected_customer = None
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

        # Horizontal split for customers list and order history
        h_split = QHBoxLayout()
        
        # Left side - Customers list
        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("Customers:"))
        self.results_list = QListWidget()
        self.results_list.setFont(font)
        self.results_list.itemClicked.connect(self.on_result_selected)
        left_panel.addWidget(self.results_list)
        
        # Right side - Order history panel
        right_panel = QVBoxLayout()
        self.order_history_label = QLabel("Order History for: (no customer selected)")
        self.order_history_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        right_panel.addWidget(self.order_history_label)
        
        # Outstanding balance line (Feature 1f)
        self.balance_line = QLabel("Outstanding balance: GH₵ 0.00")
        self.balance_line.setFont(QFont("Segoe UI", 10))
        right_panel.addWidget(self.balance_line)
        
        self.orders_table = QTableWidget()
        self.orders_table.setColumnCount(7)
        self.orders_table.setHorizontalHeaderLabels([
            "Order ID", "Invoice No.", "Date", "Status", "Total (GH₵)", "Paid (GH₵)", "Balance (GH₵)"
        ])
        self.orders_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.orders_table.horizontalHeader().setStretchLastSection(True)
        self.orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        right_panel.addWidget(self.orders_table)
        
        h_split.addLayout(left_panel, 1)
        h_split.addLayout(right_panel, 1)
        main.addLayout(h_split)

        # Create customer group
        create_group = QGroupBox("Create Customer")
        cf = QFormLayout()
        self.name_input = QLineEdit()
        self.phone_input = QLineEdit()
        
        # Customer type dropdown
        self.customer_type_combo = QComboBox()
        self.customer_type_combo.addItems(["individual", "corporate", "loyal", "first_time", "student"])
        self.customer_type_combo.setCurrentText("individual")
        
        self.notes_input = QTextEdit()
        self.notes_input.setFixedHeight(80)
        cf.addRow("Name:", self.name_input)
        cf.addRow("Phone:", self.phone_input)
        cf.addRow("Customer Type:", self.customer_type_combo)
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
        """Load recent customers via DB query."""
        try:
            conn = database.connect_db()
            cur = conn.cursor()
            cur.execute("SELECT customer_id, name, phone, customer_type, created_at FROM customers ORDER BY created_at DESC LIMIT ?", (limit,))
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

        results = None
        try:
            if hasattr(models, "find_customers"):
                results = models.find_customers(q)
        except Exception:
            results = None

        if results is None:
            try:
                conn = database.connect_db()
                cur = conn.cursor()
                like = f"%{q}%"
                cur.execute("SELECT customer_id, name, phone, customer_type, created_at FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY created_at DESC LIMIT 200", (like, like))
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
        customer_type = self.customer_type_combo.currentText()
        
        if not name:
            QMessageBox.warning(self, "Missing name", "Please enter customer name.")
            return
        try:
            cid = models.create_customer(name, phone, customer_type)
        except Exception as e:
            QMessageBox.critical(self, "Create failed", f"Failed to create customer: {e}")
            return
        QMessageBox.information(self, "Customer created", f"Customer created with id {cid}.")
        self.name_input.clear()
        self.phone_input.clear()
        self.notes_input.clear()
        self.customer_type_combo.setCurrentText("individual")
        self.load_recent_customers()
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
        
        customer_id = d.get('customer_id')
        customer_name = d.get('name', 'Unknown')
        self.order_history_label.setText(f"Order History for: {customer_name}")
        
        # Load orders and outstanding balance
        self.load_customer_orders(customer_id)
        self.load_customer_balance(customer_id, customer_name)

    def load_customer_balance(self, customer_id: int, customer_name: str):
        """Load and display customer's outstanding balance."""
        try:
            balance = models.get_customer_outstanding_balance(customer_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load balance: {e}")
            return
        
        balance_text = f"Outstanding balance: GH₵ {balance:.2f}"
        self.balance_line.setText(balance_text)
        if balance > 0.01:
            self.balance_line.setStyleSheet("color: red; font-weight: bold;")
        elif balance < -0.01:
            self.balance_line.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.balance_line.setStyleSheet("color: black;")

    def load_customer_orders(self, customer_id: int):
        """Load and display order history for the selected customer."""
        try:
            orders = models.get_orders_by_customer(customer_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load orders: {e}")
            return
        
        self.orders_table.setRowCount(0)
        
        if not orders:
            self.orders_table.setRowCount(1)
            self.orders_table.setSpan(0, 0, 1, 7)
            item = QTableWidgetItem("No orders found for this customer.")
            item.setTextAlignment(Qt.AlignCenter)
            self.orders_table.setItem(0, 0, item)
            return
        
        self.orders_table.setRowCount(len(orders))
        for i, order in enumerate(orders):
            self.orders_table.setItem(i, 0, QTableWidgetItem(str(order.get('order_id', ''))))
            
            try:
                invoice_no = models.format_invoice_number(
                    order.get('order_id'), 
                    order.get('order_date')
                )
            except:
                invoice_no = f"ORD-{order.get('order_id', '')}"
            self.orders_table.setItem(i, 1, QTableWidgetItem(invoice_no))
            
            order_date = order.get('order_date', '')
            if order_date and ' ' in order_date:
                order_date = order_date.split(' ')[0]
            self.orders_table.setItem(i, 2, QTableWidgetItem(order_date))
            
            self.orders_table.setItem(i, 3, QTableWidgetItem(str(order.get('status', ''))))
            
            total = order.get('total_amount', 0)
            self.orders_table.setItem(i, 4, QTableWidgetItem(f"{float(total):.2f}"))
            
            paid = order.get('paid_amount', 0)
            self.orders_table.setItem(i, 5, QTableWidgetItem(f"{float(paid):.2f}"))
            
            balance = order.get('balance', 0)
            self.orders_table.setItem(i, 6, QTableWidgetItem(f"{float(balance):.2f}"))

if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = CustomersWidget()
    w.show()
    sys.exit(app.exec_())
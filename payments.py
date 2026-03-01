#!/usr/bin/env python3
"""
payments.py

PyQt5-based Payments UI for the Laundry Management System (LMS).

Features:
- Search/select an order by Order ID or Invoice string (e.g., ORD-20260226-000001)
- Browse recent orders (most recent 20) and pick one
- View selected order details (customer, items, totals, balance)
- Record a payment (amount + optional notes)
  - Uses models.record_payment to persist and update the order's paid_amount and balance
- View payment history for the selected order

Usage:
    python payments.py

Design notes:
- This module uses the same DAL (models.py) you already have.
- Amounts are rounded/displayed to 2 decimals. We allow partial or full payments.
- If an overpayment occurs (amount > balance) we allow it but show a warning and still record it.
- The window is sized and laid out for clarity for cashier usage.
"""

import sys
from typing import Optional, Dict, Any, List
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QGroupBox,
    QFormLayout,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QDoubleSpinBox,
    QTextEdit,
    QListWidget,
    QListWidgetItem,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

import models
import database


def fmt_money(v: float) -> str:
    return f"{v:,.2f}"


def parse_invoice_to_order_id(text: str) -> Optional[int]:
    """
    Accept an integer order id or an invoice-id string like ORD-YYYYMMDD-000123
    and return the integer order_id or None if parsing fails.
    """
    if not text:
        return None
    text = text.strip()
    # If numeric only, treat as order_id
    if text.isdigit():
        return int(text)
    # If starts with ORD-...-<number>
    if text.upper().startswith("ORD-"):
        parts = text.split("-")
        if len(parts) >= 3:
            last = parts[-1]
            # last part may be padded with zeros
            if last.isdigit():
                return int(last)
    return None


class PaymentsWindow(QWidget):
    def __init__(self, current_user: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.current_user = current_user or database.get_user_by_username("admin")
        if not self.current_user:
            raise RuntimeError("No current user available")
        self.setWindowTitle("LMS — Payments")
        self.setMinimumSize(1000, 640)
        self.selected_order_id: Optional[int] = None
        self.order_snapshot: Optional[Dict[str, Any]] = None
        self._build_ui()

    def _build_ui(self):
        font_input = QFont("Segoe UI", 11)
        font_label = QFont("Segoe UI", 10)

        main = QHBoxLayout()

        # ---- Left: Recent orders + Search ----
        left_col = QVBoxLayout()
        search_box = QGroupBox("Find Order")
        s_layout = QFormLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter order id (123) or invoice (ORD-YYYYMMDD-000123)")
        self.search_input.setFont(font_input)
        s_layout.addRow("Order / Invoice", self.search_input)
        search_btn = QPushButton("Find")
        search_btn.clicked.connect(self.find_order)
        s_layout.addRow("", search_btn)
        search_box.setLayout(s_layout)
        left_col.addWidget(search_box)

        recent_box = QGroupBox("Recent Orders (click to select)")
        recent_layout = QVBoxLayout()
        self.recent_list = QListWidget()
        self.recent_list.setFont(font_input)
        self.recent_list.itemClicked.connect(self._recent_selected)
        recent_layout.addWidget(self.recent_list)
        recent_box.setLayout(recent_layout)
        left_col.addWidget(recent_box)

        refresh_btn = QPushButton("Refresh Recent Orders")
        refresh_btn.clicked.connect(self.load_recent_orders)
        left_col.addWidget(refresh_btn)
        left_col.addStretch(1)

        # ---- Middle: Order details and items ----
        middle_col = QVBoxLayout()
        order_info_box = QGroupBox("Order Details")
        oi_layout = QFormLayout()
        self.lbl_order_id = QLabel("-")
        self.lbl_customer = QLabel("-")
        self.lbl_order_date = QLabel("-")
        self.lbl_status = QLabel("-")
        self.lbl_instructions = QLabel("-")
        for lbl in (self.lbl_order_id, self.lbl_customer, self.lbl_order_date, self.lbl_status, self.lbl_instructions):
            lbl.setFont(font_input)
        oi_layout.addRow("Order ID:", self.lbl_order_id)
        oi_layout.addRow("Customer:", self.lbl_customer)
        oi_layout.addRow("Order Date:", self.lbl_order_date)
        oi_layout.addRow("Status:", self.lbl_status)
        oi_layout.addRow("Instructions:", self.lbl_instructions)
        order_info_box.setLayout(oi_layout)
        middle_col.addWidget(order_info_box)

        items_box = QGroupBox("Items")
        items_layout = QVBoxLayout()
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(5)
        self.items_table.setHorizontalHeaderLabels(["Item", "Color", "Qty", "Unit Price", "Subtotal"])
        self.items_table.setEditTriggers(QTableWidget.NoEditTriggers)
        items_layout.addWidget(self.items_table)
        items_box.setLayout(items_layout)
        middle_col.addWidget(items_box)

        totals_box = QGroupBox("Totals")
        totals_layout = QFormLayout()
        self.lbl_subtotal = QLabel("0.00")
        self.lbl_discount = QLabel("0.00")
        self.lbl_total = QLabel("0.00")
        self.lbl_paid = QLabel("0.00")
        self.lbl_balance = QLabel("0.00")
        for lbl in (self.lbl_subtotal, self.lbl_discount, self.lbl_total, self.lbl_paid, self.lbl_balance):
            lbl.setFont(font_input)
            lbl.setAlignment(Qt.AlignRight)
        totals_layout.addRow("Subtotal:", self.lbl_subtotal)
        totals_layout.addRow("Discount:", self.lbl_discount)
        totals_layout.addRow("Total:", self.lbl_total)
        totals_layout.addRow("Paid:", self.lbl_paid)
        totals_layout.addRow("Balance:", self.lbl_balance)
        totals_box.setLayout(totals_layout)
        middle_col.addWidget(totals_box)
        middle_col.addStretch(1)

        # ---- Right: Payment form and history ----
        right_col = QVBoxLayout()
        pay_box = QGroupBox("Record Payment")
        pay_layout = QFormLayout()
        self.pay_amount = QDoubleSpinBox()
        self.pay_amount.setDecimals(2)
        self.pay_amount.setMinimum(0.01)
        self.pay_amount.setMaximum(1_000_000.00)
        self.pay_amount.setSingleStep(10.0)
        self.pay_amount.setFont(font_input)
        self.pay_notes = QTextEdit()
        self.pay_notes.setFont(font_input)
        self.pay_notes.setFixedHeight(80)
        pay_layout.addRow("Amount:", self.pay_amount)
        pay_layout.addRow("Notes:", self.pay_notes)
        record_btn = QPushButton("Record Payment")
        record_btn.clicked.connect(self.record_payment_clicked)
        pay_layout.addRow("", record_btn)
        pay_box.setLayout(pay_layout)
        right_col.addWidget(pay_box)

        history_box = QGroupBox("Payment History")
        hist_layout = QVBoxLayout()
        self.pay_table = QTableWidget()
        self.pay_table.setColumnCount(3)
        self.pay_table.setHorizontalHeaderLabels(["Date", "Amount", "Notes"])
        self.pay_table.setEditTriggers(QTableWidget.NoEditTriggers)
        hist_layout.addWidget(self.pay_table)
        history_box.setLayout(hist_layout)
        right_col.addWidget(history_box)
        right_col.addStretch(1)

        # Place columns in main layout
        main.addLayout(left_col, stretch=3)
        main.addLayout(middle_col, stretch=5)
        main.addLayout(right_col, stretch=3)
        self.setLayout(main)

        # Populate recent orders initially
        self.load_recent_orders()

    # ---- Recent orders loader ----
    def load_recent_orders(self):
        """
        Load the most recent 20 orders and show in the recent_list.
        """
        conn = database.connect_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT o.order_id, o.order_date, o.status, o.total_amount, c.name AS customer_name "
            "FROM orders o LEFT JOIN customers c ON o.customer_id = c.customer_id "
            "ORDER BY o.order_date DESC LIMIT 20"
        )
        rows = cur.fetchall()
        conn.close()
        self.recent_list.clear()
        for r in rows:
            display = f"{r['order_id']} - {r['customer_name'] or 'Unknown'} - {r['order_date'].split(' ')[0]} - {fmt_money(r['total_amount'] or 0.0)}"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, dict(r))
            self.recent_list.addItem(item)

    def _recent_selected(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        if not data:
            return
        order_id = int(data["order_id"])
        self.select_order(order_id)

    # ---- Find order by input ----
    def find_order(self):
        text = self.search_input.text().strip()
        if not text:
            QMessageBox.information(self, "Enter Order", "Enter an order id or invoice string to find.")
            return
        oid = parse_invoice_to_order_id(text)
        if oid is None:
            QMessageBox.warning(self, "Parse error", "Could not parse order id from input. Use numeric id or ORD-... format.")
            return
        # Try to select
        self.select_order(oid)

    # ---- Select and display an order ----
    def select_order(self, order_id: int):
        try:
            snap = models.get_order_with_items(order_id)
        except Exception as e:
            QMessageBox.critical(self, "Order not found", f"Could not load order {order_id}: {e}")
            return
        self.selected_order_id = order_id
        self.order_snapshot = snap
        # Fill order info
        order = snap["order"]
        customer = snap.get("customer") or {}
        self.lbl_order_id.setText(f"{order['order_id']}   ({models.format_invoice_number(order['order_id'], order['order_date'])})")
        self.lbl_customer.setText(f"{customer.get('name') or 'Unknown'} ({customer.get('phone') or ''})")
        self.lbl_order_date.setText(order.get("order_date") or "-")
        self.lbl_status.setText(order.get("status") or "-")
        self.lbl_instructions.setText(order.get("special_instructions") or "-")

        # Items table
        items = snap.get("items", [])
        self.items_table.setRowCount(len(items))
        for i, it in enumerate(items):
            self.items_table.setItem(i, 0, QTableWidgetItem(str(it.get("item_type") or "")))
            self.items_table.setItem(i, 1, QTableWidgetItem(str(it.get("color_category") or "")))
            self.items_table.setItem(i, 2, QTableWidgetItem(str(it.get("quantity") or 0)))
            self.items_table.setItem(i, 3, QTableWidgetItem(fmt_money(float(it.get("unit_price") or 0.0))))
            self.items_table.setItem(i, 4, QTableWidgetItem(fmt_money(float(it.get("subtotal") or 0.0))))

        # Totals (ensure totals are up-to-date)
        totals = models.compute_order_totals(order_id)
        self.lbl_subtotal.setText(fmt_money(totals["subtotal"]))
        self.lbl_discount.setText(fmt_money(totals["discount_amount"]))
        self.lbl_total.setText(fmt_money(totals["total_amount"]))
        self.lbl_paid.setText(fmt_money(totals["paid_amount"]))
        self.lbl_balance.setText(fmt_money(totals["balance"]))

        # Populate payment history
        payments = snap.get("payments", [])
        self.pay_table.setRowCount(len(payments))
        for i, p in enumerate(payments):
            self.pay_table.setItem(i, 0, QTableWidgetItem(str(p.get("payment_date") or "")))
            self.pay_table.setItem(i, 1, QTableWidgetItem(fmt_money(float(p.get("amount") or 0.0))))
            self.pay_table.setItem(i, 2, QTableWidgetItem(str(p.get("notes") or "")))

    # ---- Record payment handler ----
    def record_payment_clicked(self):
        if not self.selected_order_id:
            QMessageBox.warning(self, "No order", "Select an order to record payment for.")
            return
        amount = float(self.pay_amount.value() or 0.0)
        notes = self.pay_notes.toPlainText().strip() or None
        if amount <= 0:
            QMessageBox.warning(self, "Invalid amount", "Enter an amount greater than zero.")
            return

        # Fetch current balance to warn about overpayment
        balances = models.compute_order_totals(self.selected_order_id)
        current_balance = float(balances["balance"])
        if amount > (current_balance + 0.0001):
            # Warn but allow
            res = QMessageBox.question(
                self,
                "Overpayment",
                f"Payment amount ({fmt_money(amount)}) exceeds current balance ({fmt_money(current_balance)}).\nDo you want to continue?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if res != QMessageBox.Yes:
                return

        try:
            payment_id = models.record_payment(self.selected_order_id, amount, notes)
        except Exception as e:
            QMessageBox.critical(self, "Recording error", f"Failed to record payment: {e}")
            return

        # Clear payment form
        self.pay_amount.setValue(0.0)
        self.pay_notes.clear()

        # Refresh order snapshot and UI
        self.select_order(self.selected_order_id)
        QMessageBox.information(self, "Payment recorded", f"Payment recorded (id={payment_id}).")

    # ---- Utility: expose as standalone window ----
def main():
    app = QApplication(sys.argv)
    admin = database.get_user_by_username("admin")
    win = PaymentsWindow(current_user=admin)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
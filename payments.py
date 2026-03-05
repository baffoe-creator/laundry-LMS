#!/usr/bin/env python3
"""
payments.py

PyQt5-based Payments UI for the Laundry Management System (LMS).

Features:
- Search/select an order by Order ID or Invoice string
- Browse recent orders and pick one
- View selected order details (customer, items, totals, balance)
- Record a payment (amount + optional notes)
- View payment history for the selected order
- Customer Ledger panel showing outstanding balance and recent ledger entries (Feature 1e)
- Post Adjustment button for admin/manager roles

Design notes:
- Amounts are rounded/displayed to 2 decimals.
- Ledger panel shows running balance with color coding.
- Adjustments only available to admin/manager.
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
    QDialog,
    QDialogButtonBox,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

import models
import database


def fmt_money(v: float) -> str:
    return f"{v:,.2f}"


def parse_invoice_to_order_id(text: str) -> Optional[int]:
    """Accept integer order id or invoice string and return order_id."""
    if not text:
        return None
    text = text.strip()
    if text.isdigit():
        return int(text)
    if text.upper().startswith("ORD-"):
        parts = text.split("-")
        if len(parts) >= 3:
            last = parts[-1]
            if last.isdigit():
                return int(last)
    return None


class AdjustmentDialog(QDialog):
    """Dialog for posting manual ledger adjustments (admin/manager only)."""
    
    def __init__(self, customer_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Post Ledger Adjustment")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel(f"Customer: {customer_name}"))
        layout.addWidget(QLabel("Enter amount (positive = add to debt, negative = reduce debt):"))
        
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setDecimals(2)
        self.amount_spin.setMinimum(-999999.99)
        self.amount_spin.setMaximum(999999.99)
        self.amount_spin.setValue(0.00)
        layout.addWidget(self.amount_spin)
        
        layout.addWidget(QLabel("Notes (required):"))
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Reason for adjustment")
        self.notes_edit.setMaximumHeight(80)
        layout.addWidget(self.notes_edit)
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        
        self.setLayout(layout)
    
    def get_values(self) -> tuple:
        return (self.amount_spin.value(), self.notes_edit.toPlainText().strip())


class PaymentsWindow(QWidget):
    def __init__(self, current_user: Optional[Dict[str, Any]] = None):
        super().__init__()
        # Handle both dict and sqlite3.Row
        if current_user is None:
            current_user = database.get_user_by_username("admin")
        
        # Convert sqlite3.Row to dict if needed
        if hasattr(current_user, 'keys') and not isinstance(current_user, dict):
            self.current_user = dict(current_user)
        else:
            self.current_user = current_user or {}
            
        if not self.current_user:
            raise RuntimeError("No current user available")
        
        self.role = str(self.current_user.get("role", "cashier")).lower()
        self.setWindowTitle("LMS — Payments")
        self.setMinimumSize(1200, 700)
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

        # Payment history table
        history_box = QGroupBox("Payment History")
        hist_layout = QVBoxLayout()
        self.pay_table = QTableWidget()
        self.pay_table.setColumnCount(3)
        self.pay_table.setHorizontalHeaderLabels(["Date", "Amount", "Notes"])
        self.pay_table.setEditTriggers(QTableWidget.NoEditTriggers)
        hist_layout.addWidget(self.pay_table)
        history_box.setLayout(hist_layout)
        middle_col.addWidget(history_box)
        
        middle_col.addStretch(1)

        # ---- Right: Payment form and Customer Ledger ----
        right_col = QVBoxLayout()
        
        # Payment form
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
        self.pay_notes.setFixedHeight(60)
        pay_layout.addRow("Amount:", self.pay_amount)
        pay_layout.addRow("Notes:", self.pay_notes)
        record_btn = QPushButton("Record Payment")
        record_btn.clicked.connect(self.record_payment_clicked)
        pay_layout.addRow("", record_btn)
        pay_box.setLayout(pay_layout)
        right_col.addWidget(pay_box)

        # Customer Ledger panel (Feature 1e)
        ledger_box = QGroupBox("Customer Ledger — Outstanding Balance")
        ledger_layout = QVBoxLayout()
        
        # Outstanding balance display
        self.balance_label = QLabel("Total owed: GH₵ 0.00")
        self.balance_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        ledger_layout.addWidget(self.balance_label)
        
        # Post Adjustment button (admin/manager only)
        if self.role in ("admin", "manager"):
            self.adjust_btn = QPushButton("Post Adjustment")
            self.adjust_btn.clicked.connect(self.post_adjustment_clicked)
            ledger_layout.addWidget(self.adjust_btn)
        
        # Ledger entries table
        self.ledger_table = QTableWidget()
        self.ledger_table.setColumnCount(6)
        self.ledger_table.setHorizontalHeaderLabels([
            "Date", "Type", "Amount (GH₵)", "Running Balance (GH₵)", "Order ID", "Notes"
        ])
        self.ledger_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.ledger_table.horizontalHeader().setStretchLastSection(True)
        ledger_layout.addWidget(self.ledger_table)
        
        ledger_box.setLayout(ledger_layout)
        right_col.addWidget(ledger_box)
        right_col.addStretch(1)

        # Place columns in main layout
        main.addLayout(left_col, stretch=2)
        main.addLayout(middle_col, stretch=4)
        main.addLayout(right_col, stretch=3)
        self.setLayout(main)

        # Populate recent orders initially
        self.load_recent_orders()

    # ---- Recent orders loader ----
    def load_recent_orders(self):
        """Load the most recent 20 orders and show in the recent_list."""
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
        self.select_order(oid)

    # ---- Customer Ledger methods (Feature 1e) ----
    def load_customer_ledger(self, customer_id: int, customer_name: str):
        """Load and display customer ledger entries."""
        try:
            balance = models.get_customer_outstanding_balance(customer_id)
            ledger = models.get_customer_ledger(customer_id, limit=20)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load ledger: {e}")
            return
        
        # Update balance label with color coding
        balance_text = f"Total owed by {customer_name}: GH₵ {fmt_money(balance)}"
        self.balance_label.setText(balance_text)
        if balance > 0.01:
            self.balance_label.setStyleSheet("color: red;")
        elif balance < -0.01:
            self.balance_label.setStyleSheet("color: green;")
        else:
            self.balance_label.setStyleSheet("color: black;")
        
        # Populate ledger table
        self.ledger_table.setRowCount(len(ledger))
        for i, entry in enumerate(ledger):
            # Date
            date_str = entry.get("entry_date", "")
            if date_str and " " in date_str:
                date_str = date_str.split(" ")[0]
            self.ledger_table.setItem(i, 0, QTableWidgetItem(date_str))
            
            # Type with color coding
            entry_type = entry.get("entry_type", "")
            type_item = QTableWidgetItem(entry_type)
            if entry_type == "charge":
                type_item.setForeground(QColor(255, 0, 0))  # Red
            elif entry_type == "payment":
                type_item.setForeground(QColor(0, 128, 0))  # Green
            elif entry_type == "adjustment":
                type_item.setForeground(QColor(255, 165, 0))  # Orange
            self.ledger_table.setItem(i, 1, type_item)
            
            # Amount
            amount = entry.get("amount", 0)
            amount_item = QTableWidgetItem(fmt_money(abs(amount)))
            if amount > 0:
                amount_item.setForeground(QColor(255, 0, 0))  # Red for positive (debt)
            elif amount < 0:
                amount_item.setForeground(QColor(0, 128, 0))  # Green for negative (payment)
            self.ledger_table.setItem(i, 2, amount_item)
            
            # Running balance
            self.ledger_table.setItem(i, 3, QTableWidgetItem(fmt_money(entry.get("running_balance", 0))))
            
            # Order ID
            order_id = entry.get("order_id", "")
            self.ledger_table.setItem(i, 4, QTableWidgetItem(str(order_id) if order_id else ""))
            
            # Notes
            self.ledger_table.setItem(i, 5, QTableWidgetItem(entry.get("notes", "")))

    def post_adjustment_clicked(self):
        """Handle Post Adjustment button click."""
        if not self.selected_order_id or not self.order_snapshot:
            QMessageBox.warning(self, "No order", "Select an order first.")
            return
        
        customer = self.order_snapshot.get("customer", {})
        if not customer:
            return
        
        customer_name = customer.get("name", "Unknown")
        customer_id = customer.get("customer_id")
        
        dlg = AdjustmentDialog(customer_name, self)
        if dlg.exec_() == QDialog.Accepted:
            amount, notes = dlg.get_values()
            if not notes:
                QMessageBox.warning(self, "Missing notes", "Please enter notes for this adjustment.")
                return
            
            try:
                models.post_ledger_adjustment(customer_id, amount, notes, self.selected_order_id)
                QMessageBox.information(self, "Success", "Adjustment posted successfully.")
                # Refresh ledger display
                self.load_customer_ledger(customer_id, customer_name)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to post adjustment: {e}")

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
        customer_id = customer.get("customer_id")
        customer_name = customer.get("name", "Unknown")
        
        self.lbl_order_id.setText(f"{order['order_id']}   ({models.format_invoice_number(order['order_id'], order['order_date'])})")
        self.lbl_customer.setText(f"{customer_name} ({customer.get('phone') or ''})")
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

        # Totals
        totals = models.compute_order_totals(order_id)
        self.lbl_subtotal.setText(fmt_money(totals["subtotal"]))
        self.lbl_discount.setText(fmt_money(totals["discount_amount"]))
        self.lbl_total.setText(fmt_money(totals["total_amount"]))
        self.lbl_paid.setText(fmt_money(totals["paid_amount"]))
        self.lbl_balance.setText(fmt_money(totals["balance"]))

        # Payment history
        payments = snap.get("payments", [])
        self.pay_table.setRowCount(len(payments))
        for i, p in enumerate(payments):
            self.pay_table.setItem(i, 0, QTableWidgetItem(str(p.get("payment_date") or "")))
            self.pay_table.setItem(i, 1, QTableWidgetItem(fmt_money(float(p.get("amount") or 0.0))))
            self.pay_table.setItem(i, 2, QTableWidgetItem(str(p.get("notes") or "")))

        # Load customer ledger if we have customer_id
        if customer_id:
            self.load_customer_ledger(customer_id, customer_name)

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

        balances = models.compute_order_totals(self.selected_order_id)
        current_balance = float(balances["balance"])
        if amount > (current_balance + 0.0001):
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

        self.pay_amount.setValue(0.0)
        self.pay_notes.clear()
        self.select_order(self.selected_order_id)
        QMessageBox.information(self, "Payment recorded", f"Payment recorded (id={payment_id}).")


def main():
    app = QApplication(sys.argv)
    admin = database.get_user_by_username("admin")
    win = PaymentsWindow(current_user=admin)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
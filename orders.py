#!/usr/bin/env python3
"""
orders.py

PyQt5-based Order creation UI for the Laundry Management System (LMS).

This file has been updated to integrate invoice generation directly into the Orders UI.
When an order exists, the "Print Invoice" button will:
 - Generate the invoice PDF via invoice.generate_invoice(order_id, open_file=False)
 - Present a dialog allowing the user to Open the PDF or Print it (Windows)
 - Printing uses os.startfile(path, "print") on Windows; other OSes show a helpful message.

Other functionality remains as before: create/select customer, create order, add items,
apply discount, compute totals, and finalize order.

Note: invoice.generate_invoice already exists in invoice.py and is used here to avoid duplication.
"""

from typing import Optional, Dict, Any, List
import sys
import os
import webbrowser
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QFormLayout,
    QGroupBox,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QRadioButton,
    QButtonGroup,
    QTextEdit,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

import models
import database

# Small helper to format money
def fmt_money(v: float) -> str:
    return f"{v:,.2f}"


class OrdersWindow(QWidget):
    """
    Main window for creating an order and adding items.
    Pass current_user dict (from auth) to identify created_by.
    """

    def __init__(self, current_user: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.current_user = current_user or database.get_user_by_username("admin")
        if not self.current_user:
            raise RuntimeError("No user available to create orders (expected admin or logged-in user)")

        self.order_id: Optional[int] = None
        self.order_snapshot: Optional[Dict[str, Any]] = None  # result of models.get_order_with_items
        self.setWindowTitle("LMS — Create Order")
        self.setMinimumSize(1000, 650)
        self._build_ui()

    def _build_ui(self):
        font_label = QFont("Segoe UI", 10)
        font_input = QFont("Segoe UI", 11)

        main_layout = QHBoxLayout()
        left_col = QVBoxLayout()
        middle_col = QVBoxLayout()
        right_col = QVBoxLayout()

        # ---------- Left: Customer selection ----------
        customer_box = QGroupBox("Customer")
        cb_layout = QVBoxLayout()
        form = QFormLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name or phone")
        self.search_input.setFont(font_input)
        form.addRow("Search", self.search_input)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.do_customer_search)
        form.addRow("", search_btn)

        cb_layout.addLayout(form)

        # Search results list
        self.results_list = QListWidget()
        self.results_list.setFont(font_input)
        self.results_list.setFixedHeight(140)
        cb_layout.addWidget(self.results_list)

        # Create small create-customer form
        create_form = QFormLayout()
        self.new_name = QLineEdit()
        self.new_phone = QLineEdit()
        self.new_name.setFont(font_input)
        self.new_phone.setFont(font_input)
        create_form.addRow("Name", self.new_name)
        create_form.addRow("Phone", self.new_phone)
        create_btn = QPushButton("Create Customer")
        create_btn.clicked.connect(self.create_customer)
        create_form.addRow("", create_btn)
        cb_layout.addLayout(create_form)

        customer_box.setLayout(cb_layout)
        left_col.addWidget(customer_box)

        # Selected customer display
        self.selected_customer_label = QLabel("No customer selected")
        self.selected_customer_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        left_col.addWidget(self.selected_customer_label)

        # Special instructions for order
        instr_box = QGroupBox("Special instructions")
        instr_layout = QVBoxLayout()
        self.instructions_text = QTextEdit()
        self.instructions_text.setPlaceholderText("e.g., No starch; handle with care")
        self.instructions_text.setFont(font_input)
        instr_layout.addWidget(self.instructions_text)
        instr_box.setLayout(instr_layout)
        left_col.addWidget(instr_box)

        # Create order controls
        self.create_order_btn = QPushButton("Create Order")
        self.create_order_btn.setFont(font_input)
        self.create_order_btn.clicked.connect(self.create_order)
        left_col.addWidget(self.create_order_btn)

        # Show created order id / invoice number
        self.order_info_label = QLabel("")
        self.order_info_label.setFont(QFont("Segoe UI", 10))
        left_col.addWidget(self.order_info_label)

        left_col.addStretch(1)

        # ---------- Middle: Items table and add item form ----------
        items_box = QGroupBox("Order Items")
        items_layout = QVBoxLayout()

        # Table showing items
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(5)
        self.items_table.setHorizontalHeaderLabels(["Item Type", "Color", "Quantity", "Unit Price", "Subtotal"])
        self.items_table.setEditTriggers(QTableWidget.NoEditTriggers)
        items_layout.addWidget(self.items_table)

        # Add item form
        add_form = QFormLayout()
        self.item_type_input = QLineEdit()
        self.color_input = QLineEdit()
        self.qty_input = QSpinBox()
        self.qty_input.setMinimum(1)
        self.qty_input.setValue(1)
        self.unit_price_input = QDoubleSpinBox()
        self.unit_price_input.setMinimum(0.0)
        self.unit_price_input.setDecimals(2)
        self.unit_price_input.setSingleStep(0.25)
        add_form.addRow("Item Type", self.item_type_input)
        add_form.addRow("Color Category", self.color_input)
        add_form.addRow("Quantity", self.qty_input)
        add_form.addRow("Unit Price", self.unit_price_input)

        add_btn = QPushButton("Add Item")
        add_btn.clicked.connect(self.add_item_clicked)
        add_form.addRow("", add_btn)

        items_layout.addLayout(add_form)
        items_box.setLayout(items_layout)
        middle_col.addWidget(items_box)

        # ---------- Right: Totals, Discount, Actions ----------
        totals_box = QGroupBox("Totals & Actions")
        totals_layout = QFormLayout()

        self.subtotal_lbl = QLabel("0.00")
        self.discount_lbl = QLabel("0.00")
        self.total_lbl = QLabel("0.00")
        self.paid_lbl = QLabel("0.00")
        self.balance_lbl = QLabel("0.00")

        for lbl in (self.subtotal_lbl, self.discount_lbl, self.total_lbl, self.paid_lbl, self.balance_lbl):
            lbl.setFont(font_input)
            lbl.setAlignment(Qt.AlignRight)

        totals_layout.addRow("Subtotal:", self.subtotal_lbl)
        totals_layout.addRow("Discount:", self.discount_lbl)
        totals_layout.addRow("Total:", self.total_lbl)
        totals_layout.addRow("Paid:", self.paid_lbl)
        totals_layout.addRow("Balance:", self.balance_lbl)

        # Discount controls (Percent / Fixed)
        disc_group = QGroupBox("Discount")
        dg_layout = QVBoxLayout()
        self.rb_percent = QRadioButton("Percent (%)")
        self.rb_fixed = QRadioButton("Fixed amount")
        self.rb_fixed.setChecked(True)
        self.discount_btns = QButtonGroup()
        self.discount_btns.addButton(self.rb_percent)
        self.discount_btns.addButton(self.rb_fixed)
        dg_layout.addWidget(self.rb_percent)
        dg_layout.addWidget(self.rb_fixed)
        self.discount_value = QDoubleSpinBox()
        self.discount_value.setDecimals(2)
        self.discount_value.setMinimum(0.00)
        self.discount_value.setMaximum(1000000.00)
        self.discount_value.setSingleStep(1.00)
        dg_layout.addWidget(self.discount_value)
        disc_group.setLayout(dg_layout)

        totals_layout.addRow(disc_group)

        # Buttons
        apply_disc_btn = QPushButton("Apply / Update Discount")
        apply_disc_btn.clicked.connect(self.apply_discount_clicked)
        totals_layout.addRow("", apply_disc_btn)

        finalize_btn = QPushButton("Finalize Order")
        finalize_btn.clicked.connect(self.finalize_order_clicked)
        totals_layout.addRow("", finalize_btn)

        # Integrated invoice generation: now opens a dialog allowing Open / Print
        print_btn = QPushButton("Print Invoice")
        print_btn.clicked.connect(self.print_invoice_clicked)
        totals_layout.addRow("", print_btn)

        totals_box.setLayout(totals_layout)
        right_col.addWidget(totals_box)
        right_col.addStretch(1)

        # Pack columns into main layout
        main_layout.addLayout(left_col, stretch=3)
        main_layout.addLayout(middle_col, stretch=5)
        main_layout.addLayout(right_col, stretch=2)
        self.setLayout(main_layout)

        # Initial state: disable item controls until order created
        self._set_items_enabled(False)

    # --------- Customer helpers ---------
    def do_customer_search(self):
        q = self.search_input.text().strip()
        if not q:
            QMessageBox.information(self, "Empty search", "Enter a name or phone to search.")
            return
        results = models.find_customers(q)
        self.results_list.clear()
        if not results:
            QMessageBox.information(self, "No results", "No customers found. Create a new customer.")
            return
        for r in results:
            item = QListWidgetItem(f"{r['customer_id']} - {r['name']} ({r.get('phone') or ''})")
            item.setData(Qt.UserRole, r)
            self.results_list.addItem(item)

        # Select first result automatically
        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)
            self._set_selected_customer_from_list()

        # Connect selection changes
        self.results_list.currentItemChanged.connect(lambda *_: self._set_selected_customer_from_list())

    def _set_selected_customer_from_list(self):
        item = self.results_list.currentItem()
        if not item:
            return
        r = item.data(Qt.UserRole)
        self.selected_customer = r
        self.selected_customer_label.setText(f"Selected: {r['customer_id']} - {r['name']} ({r.get('phone') or ''})")

    def create_customer(self):
        name = self.new_name.text().strip()
        phone = self.new_phone.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing name", "Please enter customer name.")
            return
        cid = models.create_customer(name, phone or None)
        QMessageBox.information(self, "Customer created", f"Customer created with id {cid}.")
        # Auto-select the newly created customer
        self.selected_customer = {"customer_id": cid, "name": name, "phone": phone}
        self.selected_customer_label.setText(f"Selected: {cid} - {name} ({phone})")
        # Clear inputs
        self.new_name.clear()
        self.new_phone.clear()

    # --------- Order lifecycle ---------
    def create_order(self):
        # Must have selected customer
        sc = getattr(self, "selected_customer", None)
        if not sc:
            QMessageBox.warning(self, "No customer", "Please select or create a customer first.")
            return
        collection_date = None  # Could add a date picker later; leave empty now
        special = self.instructions_text.toPlainText().strip() or None
        # Discount values at creation time
        disc_type = "percent" if self.rb_percent.isChecked() else "fixed"
        disc_value = float(self.discount_value.value() or 0.0)

        try:
            created_by = int(self.current_user["user_id"])
        except Exception:
            QMessageBox.critical(self, "User error", "Current user not available.")
            return

        oid = models.create_order(
            customer_id=sc["customer_id"],
            created_by=created_by,
            collection_date=collection_date,
            special_instructions=special,
            discount=disc_value,
            discount_type=disc_type,
        )
        self.order_id = oid
        # Fetch full snapshot for display
        self.refresh_order_snapshot()
        inv = models.format_invoice_number(self.order_id, self.order_snapshot["order"]["order_date"])
        self.order_info_label.setText(f"Order created: ID={self.order_id}  Invoice={inv}")
        QMessageBox.information(self, "Order created", f"Order created (order_id={self.order_id}).")
        # Enable item controls
        self._set_items_enabled(True)

    def _set_items_enabled(self, enabled: bool):
        self.item_type_input.setEnabled(enabled)
        self.color_input.setEnabled(enabled)
        self.qty_input.setEnabled(enabled)
        self.unit_price_input.setEnabled(enabled)

    def add_item_clicked(self):
        if not self.order_id:
            QMessageBox.warning(self, "No order", "Create an order before adding items.")
            return
        item_type = self.item_type_input.text().strip()
        color = self.color_input.text().strip()
        qty = int(self.qty_input.value())
        unit_price = float(self.unit_price_input.value())

        if not item_type:
            QMessageBox.warning(self, "Missing item", "Enter item type (e.g., Shirt).")
            return

        try:
            item_id = models.add_order_item(self.order_id, item_type, color or None, qty, unit_price)
        except Exception as e:
            QMessageBox.critical(self, "Error adding item", str(e))
            return

        # Clear fields after add
        self.item_type_input.clear()
        self.color_input.clear()
        self.qty_input.setValue(1)
        self.unit_price_input.setValue(0.0)

        # Refresh display
        self.refresh_order_snapshot()
        QMessageBox.information(self, "Item added", f"Item added (id={item_id}).")

    def refresh_order_snapshot(self):
        if not self.order_id:
            return
        try:
            snap = models.get_order_with_items(self.order_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load order: {e}")
            return
        self.order_snapshot = snap
        # Update items table
        items: List[Dict[str, Any]] = snap["items"]
        self.items_table.setRowCount(len(items))
        for i, it in enumerate(items):
            self.items_table.setItem(i, 0, QTableWidgetItem(str(it.get("item_type"))))
            self.items_table.setItem(i, 1, QTableWidgetItem(str(it.get("color_category") or "")))
            self.items_table.setItem(i, 2, QTableWidgetItem(str(it.get("quantity"))))
            self.items_table.setItem(i, 3, QTableWidgetItem(fmt_money(float(it.get("unit_price") or 0.0))))
            self.items_table.setItem(i, 4, QTableWidgetItem(fmt_money(float(it.get("subtotal") or 0.0))))

        # Update totals by calling compute_order_totals to ensure DB values are current
        totals = models.compute_order_totals(self.order_id)
        # totals keys: subtotal, discount_amount, total_amount, paid_amount, balance
        self.subtotal_lbl.setText(fmt_money(totals["subtotal"]))
        self.discount_lbl.setText(fmt_money(totals["discount_amount"]))
        self.total_lbl.setText(fmt_money(totals["total_amount"]))
        self.paid_lbl.setText(fmt_money(totals["paid_amount"]))
        self.balance_lbl.setText(fmt_money(totals["balance"]))

        # Also set discount UI to reflect current order settings
        order = snap["order"]
        if order:
            disc = float(order.get("discount") or 0.0)
            dtype = order.get("discount_type") or "fixed"
            self.discount_value.setValue(disc)
            if dtype == "percent":
                self.rb_percent.setChecked(True)
            else:
                self.rb_fixed.setChecked(True)

    # --------- Discount update helper ---------
    def apply_discount_clicked(self):
        if not self.order_id:
            QMessageBox.warning(self, "No order", "Create an order before applying discount.")
            return
        disc = float(self.discount_value.value() or 0.0)
        dtype = "percent" if self.rb_percent.isChecked() else "fixed"
        # Update orders table directly and recompute totals
        conn = database.connect_db()
        cur = conn.cursor()
        cur.execute("UPDATE orders SET discount = ?, discount_type = ? WHERE order_id = ?", (disc, dtype, self.order_id))
        conn.commit()
        conn.close()
        # Recompute totals and refresh
        totals = models.compute_order_totals(self.order_id)
        self.refresh_order_snapshot()
        QMessageBox.information(self, "Discount applied", f"Discount updated ({dtype} {disc}).")

    def finalize_order_clicked(self):
        """
        Finalize order action. For now this is a placeholder that sets status to 'Received'
        (the default) and reminds cashier to take payment or print invoice.
        """
        if not self.order_id:
            QMessageBox.warning(self, "No order", "Create and add items to the order first.")
            return
        conn = database.connect_db()
        cur = conn.cursor()
        # For now keep status as-is, but you might update it here.
        cur.execute("UPDATE orders SET status = ? WHERE order_id = ?", ("Received", self.order_id))
        conn.commit()
        conn.close()
        QMessageBox.information(self, "Order finalized", "Order finalized. You can now record payment or print invoice.")

    # --------- Integrated invoice generation & printing ---------
    def print_invoice_clicked(self):
        if not self.order_id:
            QMessageBox.warning(self, "No order", "Create an order before printing invoice.")
            return
        # Lazy import invoice so module isn't required until this action
        try:
            import invoice  # invoice.generate_invoice(...)
        except Exception:
            QMessageBox.information(self, "Invoice not available", "Invoice module not found or not implemented. Please ensure invoice.py exists.")
            return

        try:
            # Generate invoice but do NOT auto-open (we'll offer Open/Print choices)
            outfile = invoice.generate_invoice(self.order_id, open_file=False)
        except Exception as e:
            QMessageBox.critical(self, "Invoice error", f"Failed to generate invoice: {e}")
            return

        # Show dialog offering to Open or Print the PDF
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Invoice Generated")
        dlg.setText(f"Invoice saved to:\n{outfile}\n\nWould you like to open the file or send it to the printer?")
        open_btn = dlg.addButton("Open", QMessageBox.AcceptRole)
        print_btn = dlg.addButton("Print", QMessageBox.ActionRole)
        close_btn = dlg.addButton("Close", QMessageBox.RejectRole)
        dlg.exec_()

        clicked = dlg.clickedButton()
        if clicked == open_btn:
            # Open with system default app
            try:
                if os.name == "nt":
                    os.startfile(outfile)
                else:
                    webbrowser.open(str(outfile))
            except Exception as e:
                QMessageBox.warning(self, "Open failed", f"Could not open file: {e}")
        elif clicked == print_btn:
            # Attempt to print (Windows supported via startfile print verb). Ask confirmation first.
            confirm = QMessageBox.question(self, "Confirm Print", "Send invoice to default printer?", QMessageBox.Yes | QMessageBox.No)
            if confirm != QMessageBox.Yes:
                return
            try:
                if os.name == "nt":
                    # This will send the PDF to the default system printer (Windows)
                    os.startfile(outfile, "print")
                else:
                    # Non-Windows printing not implemented here; advise user to open and print manually
                    QMessageBox.information(self, "Print not supported", "Automatic printing is only supported on Windows in this build. Please open the PDF and print manually.")
            except Exception as e:
                QMessageBox.warning(self, "Print failed", f"Could not print file: {e}")

if __name__ == "__main__":
    # Run as standalone for testing
    app = QApplication(sys.argv)
    # Use admin user by default (seeded during DB init)
    admin = database.get_user_by_username("admin")
    w = OrdersWindow(current_user=admin)
    w.show()
    sys.exit(app.exec_())
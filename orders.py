#!/usr/bin/env python3
"""
orders.py

PyQt5-based Order creation UI for the Laundry Management System (LMS).

 
"""

from typing import Optional, Dict, Any, List, Tuple
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
    QCheckBox,
    QButtonGroup,
    QTextEdit,
    QFrame,
    QHeaderView,
    QScrollArea,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

import models
import database


def fmt_money(v: float) -> str:
    return f"GH₵ {v:,.2f}"


def _make_scrollable(widget: QWidget) -> QScrollArea:
    """Wrap a widget in a vertically-scrollable, horizontally-fixed scroll area."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setWidget(widget)
    return scroll


class OrdersWindow(QWidget):
    def __init__(self, current_user: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.current_user = current_user or database.get_user_by_username("admin")
        if not self.current_user:
            raise RuntimeError("No user available to create orders (expected admin or logged-in user)")

        self.order_id: Optional[int] = None
        self.order_snapshot: Optional[Dict[str, Any]] = None
        self.price_catalogue: List[Dict[str, Any]] = []
        self.express_active: bool = False
        self.express_amount: float = 0.0
        self.discount_suggestion: Optional[Dict[str, Any]] = None
        self.selected_customer: Optional[Dict[str, Any]] = None
        self.setWindowTitle("LMS — Create Order")
        self.setMinimumSize(900, 580)
        self._load_price_catalogue()
        self._build_ui()

    def _load_price_catalogue(self):
        try:
            self.price_catalogue = models.get_all_prices()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load price catalogue: {e}")
            self.price_catalogue = []

    def _build_ui(self):
        font_label = QFont("Segoe UI", 10)
        font_input = QFont("Segoe UI", 11)

        main_layout = QHBoxLayout()
        main_layout.setSpacing(8)

        # ---------- Left: Customer selection ----------
        left_container = QWidget()
        left_col = QVBoxLayout(left_container)
        left_col.setContentsMargins(0, 0, 0, 0)

        customer_box = QGroupBox("Customer")
        cb_layout = QVBoxLayout()
        form = QFormLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name or phone")
        self.search_input.setFont(font_input)
        form.addRow("Search", self.search_input)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.do_customer_search)
        search_btn.setCursor(Qt.PointingHandCursor)
        form.addRow("", search_btn)

        cb_layout.addLayout(form)

        self.results_list = QListWidget()
        self.results_list.setFont(font_input)
        self.results_list.setObjectName("resultsList")
        self.results_list.setFixedHeight(140)
        self.results_list.itemClicked.connect(self.on_customer_selected)
        cb_layout.addWidget(self.results_list)

        create_form = QFormLayout()
        self.new_name = QLineEdit()
        self.new_phone = QLineEdit()
        self.new_name.setFont(font_input)
        self.new_phone.setFont(font_input)
        
        self.new_customer_type = QComboBox()
        self.new_customer_type.addItems(["individual", "corporate", "loyal", "first_time", "student"])
        self.new_customer_type.setCurrentText("individual")
        
        create_form.addRow("Name", self.new_name)
        create_form.addRow("Phone", self.new_phone)
        create_form.addRow("Type", self.new_customer_type)
        create_btn = QPushButton("Create Customer")
        create_btn.clicked.connect(self.create_customer)
        create_btn.setCursor(Qt.PointingHandCursor)
        create_form.addRow("", create_btn)
        cb_layout.addLayout(create_form)

        customer_box.setLayout(cb_layout)
        left_col.addWidget(customer_box)

        self.selected_customer_label = QLabel("No customer selected")
        self.selected_customer_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        left_col.addWidget(self.selected_customer_label)

        instr_box = QGroupBox("Special instructions")
        instr_layout = QVBoxLayout()
        self.instructions_text = QTextEdit()
        self.instructions_text.setPlaceholderText("e.g., No starch; handle with care")
        self.instructions_text.setFont(font_input)
        instr_layout.addWidget(self.instructions_text)
        instr_box.setLayout(instr_layout)
        left_col.addWidget(instr_box)

        self.create_order_btn = QPushButton("Create Order")
        self.create_order_btn.setFont(font_input)
        self.create_order_btn.clicked.connect(self.create_order)
        self.create_order_btn.setCursor(Qt.PointingHandCursor)
        self.create_order_btn.setProperty("accent", True)  # Accent button
        left_col.addWidget(self.create_order_btn)

        self.order_info_label = QLabel("")
        self.order_info_label.setFont(QFont("Segoe UI", 10))
        left_col.addWidget(self.order_info_label)

        left_col.addStretch(1)

        # ---------- Middle: Items table and add item form ----------
        middle_container = QWidget()
        middle_col = QVBoxLayout(middle_container)
        middle_col.setContentsMargins(0, 0, 0, 0)

        items_box = QGroupBox("Order Items")
        items_layout = QVBoxLayout()

        self.items_table = QTableWidget()
        self.items_table.setColumnCount(5)
        self.items_table.setHorizontalHeaderLabels([
            "Item ID", "Item Description", "Quantity", "Unit Price", "Subtotal"
        ])
        self.items_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.items_table.horizontalHeader().setStretchLastSection(True)
        self.items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.items_table.setAlternatingRowColors(True)
        self.items_table.verticalHeader().setVisible(False)
        items_layout.addWidget(self.items_table)

        add_form = QFormLayout()
        
        self.item_combo = QComboBox()
        self.item_combo.setEditable(True)
        self.item_combo.setFont(font_input)
        self.populate_item_combo()
        self.item_combo.currentTextChanged.connect(self.on_item_selected)
        add_form.addRow("Item:", self.item_combo)
        
        service_layout = QVBoxLayout()
        service_label = QLabel("Select Services (you can select multiple):")
        service_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        service_layout.addWidget(service_label)
        
        laundry_group = QGroupBox("Laundry Services")
        laundry_layout = QVBoxLayout()
        
        self.chk_laundry_coloured = QCheckBox("Laundry — Coloured")
        self.chk_laundry_white = QCheckBox("Laundry — White")
        self.chk_laundry_coloured.toggled.connect(self.update_service_prices)
        self.chk_laundry_white.toggled.connect(self.update_service_prices)
        
        laundry_layout.addWidget(self.chk_laundry_coloured)
        laundry_layout.addWidget(self.chk_laundry_white)
        laundry_group.setLayout(laundry_layout)
        service_layout.addWidget(laundry_group)
        
        pressing_group = QGroupBox("Pressing / Ironing")
        pressing_layout = QVBoxLayout()
        
        self.chk_pressing = QCheckBox("Pressing / Ironing Only")
        self.chk_pressing.toggled.connect(self.update_service_prices)
        
        pressing_layout.addWidget(self.chk_pressing)
        pressing_group.setLayout(pressing_layout)
        service_layout.addWidget(pressing_group)
        
        add_form.addRow("Services:", service_layout)
        
        price_summary_layout = QHBoxLayout()
        price_summary_layout.addWidget(QLabel("Selected services:"))
        self.price_summary_label = QLabel("None selected")
        self.price_summary_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        price_summary_layout.addWidget(self.price_summary_label)
        price_summary_layout.addStretch()
        add_form.addRow("", price_summary_layout)
        
        total_price_layout = QHBoxLayout()
        total_price_layout.addWidget(QLabel("Total price for this item:"))
        self.total_price_label = QLabel("GH₵ 0.00")
        self.total_price_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.total_price_label.setStyleSheet("color: #2c7da0;")
        total_price_layout.addWidget(self.total_price_label)
        total_price_layout.addStretch()
        add_form.addRow("", total_price_layout)
        
        self.qty_input = QSpinBox()
        self.qty_input.setMinimum(1)
        self.qty_input.setValue(1)
        self.qty_input.setFont(font_input)
        self.qty_input.valueChanged.connect(self.update_total_price)
        add_form.addRow("Quantity:", self.qty_input)
        
        self.subtotal_preview = QLabel("GH₵ 0.00")
        self.subtotal_preview.setFont(QFont("Segoe UI", 11, QFont.Bold))
        add_form.addRow("Subtotal:", self.subtotal_preview)

        add_btn = QPushButton("Add to Order")
        add_btn.clicked.connect(self.add_item_clicked)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_form.addRow("", add_btn)

        remove_layout = QHBoxLayout()
        self.remove_item_combo = QComboBox()
        self.remove_item_combo.setFont(font_input)
        self.remove_item_combo.setMinimumWidth(200)
        remove_layout.addWidget(QLabel("Remove item:"))
        remove_layout.addWidget(self.remove_item_combo)
        remove_btn = QPushButton("Remove Selected Item")
        remove_btn.clicked.connect(self.remove_selected_item)
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_layout.addWidget(remove_btn)
        remove_layout.addStretch()
        items_layout.addLayout(remove_layout)

        items_layout.addLayout(add_form)
        items_box.setLayout(items_layout)
        middle_col.addWidget(items_box)

        # ---------- Right: Totals, Discount, Actions ----------
        right_container = QWidget()
        right_col = QVBoxLayout(right_container)
        right_col.setContentsMargins(0, 0, 0, 0)

        totals_box = QGroupBox("Totals & Actions")
        totals_layout = QFormLayout()

        self.subtotal_lbl = QLabel("0.00")
        self.express_lbl = QLabel("0.00")
        self.discount_lbl = QLabel("0.00")
        self.total_lbl = QLabel("0.00")
        self.paid_lbl = QLabel("0.00")
        self.balance_lbl = QLabel("0.00")

        for lbl in (self.subtotal_lbl, self.express_lbl, self.discount_lbl, 
                   self.total_lbl, self.paid_lbl, self.balance_lbl):
            lbl.setFont(font_input)
            lbl.setAlignment(Qt.AlignRight)

        totals_layout.addRow("Subtotal:", self.subtotal_lbl)
        
        express_row = QHBoxLayout()
        self.express_checkbox = QCheckBox("Express Service")
        self.express_checkbox.setFont(font_input)
        self.express_checkbox.toggled.connect(self.on_express_toggled)
        express_row.addWidget(self.express_checkbox)
        express_row.addWidget(QLabel("Surcharge:"))
        express_row.addWidget(self.express_lbl)
        express_row.addStretch()
        totals_layout.addRow("", express_row)
        
        totals_layout.addRow("Discount:", self.discount_lbl)
        totals_layout.addRow("Total:", self.total_lbl)
        totals_layout.addRow("Paid:", self.paid_lbl)
        totals_layout.addRow("Balance:", self.balance_lbl)

        discount_suggest_box = QGroupBox("Suggested Discount")
        ds_layout = QVBoxLayout()
        self.discount_suggest_label = QLabel("No discount applicable")
        self.discount_suggest_label.setWordWrap(True)
        ds_layout.addWidget(self.discount_suggest_label)
        
        self.apply_discount_btn = QPushButton("Apply Suggested Discount")
        self.apply_discount_btn.clicked.connect(self.apply_suggested_discount)
        self.apply_discount_btn.setCursor(Qt.PointingHandCursor)
        self.apply_discount_btn.setEnabled(False)
        ds_layout.addWidget(self.apply_discount_btn)
        discount_suggest_box.setLayout(ds_layout)
        totals_layout.addRow(discount_suggest_box)

        disc_group = QGroupBox("Manual Discount")
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

        apply_disc_btn = QPushButton("Apply / Update Discount")
        apply_disc_btn.clicked.connect(self.apply_discount_clicked)
        apply_disc_btn.setCursor(Qt.PointingHandCursor)
        totals_layout.addRow("", apply_disc_btn)

        finalize_btn = QPushButton("Finalize Order")
        finalize_btn.clicked.connect(self.finalize_order_clicked)
        finalize_btn.setCursor(Qt.PointingHandCursor)
        finalize_btn.setProperty("accent", True)  # Accent button
        totals_layout.addRow("", finalize_btn)

        print_btn = QPushButton("Print Invoice")
        print_btn.clicked.connect(self.print_invoice_clicked)
        print_btn.setCursor(Qt.PointingHandCursor)
        totals_layout.addRow("", print_btn)

        totals_box.setLayout(totals_layout)
        right_col.addWidget(totals_box)
        right_col.addStretch(1)

        # Wrap columns in scroll areas
        left_scroll = _make_scrollable(left_container)
        left_scroll.setMinimumWidth(200)
        middle_scroll = _make_scrollable(middle_container)
        middle_scroll.setMinimumWidth(320)
        right_scroll = _make_scrollable(right_container)
        right_scroll.setMinimumWidth(220)

        main_layout.addWidget(left_scroll, stretch=2)
        main_layout.addWidget(middle_scroll, stretch=4)
        main_layout.addWidget(right_scroll, stretch=3)
        self.setLayout(main_layout)

        self._set_items_enabled(False)
        self.express_checkbox.setEnabled(False)

    # ... (rest of the methods remain exactly the same as before) ...

    def _set_items_enabled(self, enabled: bool):
        self.item_combo.setEnabled(enabled)
        self.chk_laundry_coloured.setEnabled(enabled)
        self.chk_laundry_white.setEnabled(enabled)
        self.chk_pressing.setEnabled(enabled)
        self.qty_input.setEnabled(enabled)

    def on_customer_selected(self, item: QListWidgetItem):
        r = item.data(Qt.UserRole)
        self.selected_customer = r
        cust_type = r.get('customer_type', 'individual')
        self.selected_customer_label.setText(
            f"Selected: {r['customer_id']} - {r['name']} ({r.get('phone') or ''}) [{cust_type}]"
        )
        
        if self.order_id:
            self.update_discount_suggestion()

    def populate_item_combo(self):
        self.item_combo.clear()
        for item in self.price_catalogue:
            self.item_combo.addItem(item['item_name'])

    def on_item_selected(self, item_name: str):
        if not item_name:
            return
        
        selected_item = None
        for item in self.price_catalogue:
            if item['item_name'] == item_name:
                selected_item = item
                break
        
        if not selected_item:
            return
        
        self.chk_laundry_coloured.setEnabled(selected_item['price_coloured'] is not None)
        self.chk_laundry_white.setEnabled(selected_item['price_white'] is not None)
        self.chk_pressing.setEnabled(selected_item['price_pressing'] is not None)
        
        self.chk_laundry_coloured.setToolTip("" if selected_item['price_coloured'] is not None else "Not available for this item")
        self.chk_laundry_white.setToolTip("" if selected_item['price_white'] is not None else "Not available for this item")
        self.chk_pressing.setToolTip("" if selected_item['price_pressing'] is not None else "Not available for this item")
        
        if not self.chk_laundry_coloured.isEnabled():
            self.chk_laundry_coloured.setChecked(False)
        if not self.chk_laundry_white.isEnabled():
            self.chk_laundry_white.setChecked(False)
        if not self.chk_pressing.isEnabled():
            self.chk_pressing.setChecked(False)
        
        self.update_service_prices()

    def update_service_prices(self):
        if not self.item_combo.currentText():
            self.price_summary_label.setText("None selected")
            self.total_price_label.setText("GH₵ 0.00")
            self.update_total_price()
            return
        
        item_name = self.item_combo.currentText()
        selected_item = None
        for item in self.price_catalogue:
            if item['item_name'] == item_name:
                selected_item = item
                break
        
        if not selected_item:
            return
        
        total_price = 0.0
        selected_services = []
        
        if self.chk_laundry_coloured.isChecked() and selected_item['price_coloured'] is not None:
            total_price += selected_item['price_coloured']
            selected_services.append("Coloured")
        
        if self.chk_laundry_white.isChecked() and selected_item['price_white'] is not None:
            total_price += selected_item['price_white']
            selected_services.append("White")
        
        if self.chk_pressing.isChecked() and selected_item['price_pressing'] is not None:
            total_price += selected_item['price_pressing']
            selected_services.append("Pressing")
        
        if selected_services:
            self.price_summary_label.setText(" + ".join(selected_services))
            self.total_price_label.setText(f"GH₵ {total_price:.2f}")
        else:
            self.price_summary_label.setText("None selected")
            self.total_price_label.setText("GH₵ 0.00")
        
        self.update_total_price()

    def update_total_price(self):
        try:
            price_text = self.total_price_label.text().replace("GH₵ ", "")
            unit_price = float(price_text)
            qty = self.qty_input.value()
            subtotal = unit_price * qty
            self.subtotal_preview.setText(f"GH₵ {subtotal:.2f}")
        except:
            self.subtotal_preview.setText("GH₵ 0.00")

    def get_service_description(self) -> Tuple[str, float]:
        if not self.item_combo.currentText():
            return ("", 0.0)
        
        item_name = self.item_combo.currentText()
        selected_item = None
        for item in self.price_catalogue:
            if item['item_name'] == item_name:
                selected_item = item
                break
        
        if not selected_item:
            return ("", 0.0)
        
        services = []
        total_price = 0.0
        
        if self.chk_laundry_coloured.isChecked() and selected_item['price_coloured'] is not None:
            services.append("Coloured")
            total_price += selected_item['price_coloured']
        
        if self.chk_laundry_white.isChecked() and selected_item['price_white'] is not None:
            services.append("White")
            total_price += selected_item['price_white']
        
        if self.chk_pressing.isChecked() and selected_item['price_pressing'] is not None:
            services.append("Pressing")
            total_price += selected_item['price_pressing']
        
        if not services:
            return ("", 0.0)
        
        service_str = " + ".join(services)
        description = f"{item_name} ({service_str})"
        
        return (description, total_price)

    def calculate_express_surcharge(self) -> float:
        if not self.order_id:
            return 0.0
        
        snap = models.get_order_with_items(self.order_id)
        items = snap['items']
        item_count = len(items)
        
        if item_count == 0:
            return 0.0
        elif item_count == 1:
            return float(items[0]['subtotal'])
        elif 2 <= item_count <= 3:
            return sum(float(item['subtotal']) for item in items)
        elif 4 <= item_count <= 5:
            return 15.00
        elif 6 <= item_count <= 10:
            return 25.00
        elif item_count >= 11:
            return 30.00
        else:
            return 0.00

    def update_totals_with_express(self):
        if not self.order_id:
            return
        
        totals = models.compute_order_totals(self.order_id)
        
        express_amount = self.express_amount if self.express_active else 0.0
        subtotal = totals["subtotal"]
        discount_amount = totals["discount_amount"]
        
        total_before_discount = subtotal + express_amount
        total_amount = total_before_discount - discount_amount
        
        self.subtotal_lbl.setText(fmt_money(subtotal).replace("GH₵ ", ""))
        self.express_lbl.setText(fmt_money(express_amount).replace("GH₵ ", ""))
        self.discount_lbl.setText(fmt_money(discount_amount).replace("GH₵ ", ""))
        self.total_lbl.setText(fmt_money(total_amount).replace("GH₵ ", ""))
        self.paid_lbl.setText(fmt_money(totals["paid_amount"]).replace("GH₵ ", ""))
        
        balance = total_amount - totals["paid_amount"]
        self.balance_lbl.setText(fmt_money(max(0.0, balance)).replace("GH₵ ", ""))

    def on_express_toggled(self, checked: bool):
        if not self.order_id:
            self.express_checkbox.setChecked(False)
            return
        
        if checked:
            self.express_amount = self.calculate_express_surcharge()
            if self.express_amount <= 0:
                QMessageBox.warning(self, "Cannot add express", 
                                   "Could not calculate express surcharge. Make sure you have added items first.")
                self.express_checkbox.setChecked(False)
                self.express_amount = 0.0
                return
            self.express_active = True
        else:
            self.express_active = False
            self.express_amount = 0.0
        
        self.update_totals_with_express()

    def calculate_discount_suggestion(self) -> Optional[Dict[str, Any]]:
        if not self.order_id or not hasattr(self, 'selected_customer'):
            return None
        
        customer = self.selected_customer
        if not customer:
            return None
        
        customer_type = customer.get('customer_type', 'individual')
        
        snap = models.get_order_with_items(self.order_id)
        items = snap['items']
        item_count = len(items)
        
        if customer_type == 'corporate' and item_count > 30:
            return {'percentage': 20, 'description': 'Corporate bulk (20% off)'}
        elif customer_type == 'individual' and item_count > 30:
            return {'percentage': 10, 'description': 'Large bulk (10% off)'}
        elif customer_type == 'individual' and item_count > 15:
            return {'percentage': 5, 'description': 'Medium bulk (5% off)'}
        elif customer_type == 'loyal' and item_count > 15:
            return {'percentage': 8, 'description': 'Loyal customer (8% off)'}
        elif customer_type == 'first_time':
            return {'percentage': 10, 'description': 'First-time customer (10% off)'}
        elif customer_type == 'student':
            return {'percentage': 20, 'description': 'Student discount (20% off)'}
        
        return None

    def update_discount_suggestion(self):
        suggestion = self.calculate_discount_suggestion()
        self.discount_suggestion = suggestion
        
        if suggestion:
            self.discount_suggest_label.setText(
                f"Suggested: {suggestion['description']}\n"
                f"Click 'Apply' to add this discount."
            )
            self.apply_discount_btn.setEnabled(True)
        else:
            self.discount_suggest_label.setText("No discount applicable")
            self.apply_discount_btn.setEnabled(False)

    def apply_suggested_discount(self):
        if not self.discount_suggestion or not self.order_id:
            return
        
        percentage = self.discount_suggestion['percentage']
        
        conn = database.connect_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE orders SET discount = ?, discount_type = ? WHERE order_id = ?",
            (percentage, 'percent', self.order_id)
        )
        conn.commit()
        conn.close()
        
        models.compute_order_totals(self.order_id)
        self.refresh_order_snapshot()
        
        QMessageBox.information(
            self, 
            "Discount Applied", 
            f"Applied {self.discount_suggestion['description']}"
        )

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
            item = QListWidgetItem(f"{r['customer_id']} - {r['name']} ({r.get('phone') or ''}) [{r.get('customer_type', 'individual')}]")
            item.setData(Qt.UserRole, r)
            self.results_list.addItem(item)

        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)
            self.on_customer_selected(self.results_list.item(0))

    def create_customer(self):
        name = self.new_name.text().strip()
        phone = self.new_phone.text().strip()
        customer_type = self.new_customer_type.currentText()
        
        if not name:
            QMessageBox.warning(self, "Missing name", "Please enter customer name.")
            return
        cid = models.create_customer(name, phone or None, customer_type)
        QMessageBox.information(self, "Customer created", f"Customer created with id {cid}.")
        self.selected_customer = {"customer_id": cid, "name": name, "phone": phone, "customer_type": customer_type}
        self.selected_customer_label.setText(f"Selected: {cid} - {name} ({phone}) [{customer_type}]")
        self.new_name.clear()
        self.new_phone.clear()
        self.new_customer_type.setCurrentText("individual")

    def create_order(self):
        sc = getattr(self, "selected_customer", None)
        if not sc:
            QMessageBox.warning(self, "No customer", "Please select or create a customer first.")
            return
        collection_date = None
        special = self.instructions_text.toPlainText().strip() or None
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
        self.express_active = False
        self.express_amount = 0.0
        self.refresh_order_snapshot()
        inv = models.format_invoice_number(self.order_id, self.order_snapshot["order"]["order_date"])
        self.order_info_label.setText(f"Order created: ID={self.order_id}  Invoice={inv}")
        QMessageBox.information(self, "Order created", f"Order created (order_id={self.order_id}).")
        self._set_items_enabled(True)
        self.express_checkbox.setEnabled(True)
        self.update_discount_suggestion()

    def add_item_clicked(self):
        if not self.order_id:
            QMessageBox.warning(self, "No order", "Create an order before adding items.")
            return
        
        item_name = self.item_combo.currentText().strip()
        if not item_name:
            QMessageBox.warning(self, "Missing item", "Select an item from the catalogue.")
            return
        
        description, total_price = self.get_service_description()
        if not description or total_price <= 0:
            QMessageBox.warning(self, "No service selected", "Please select at least one service for this item.")
            return
        
        qty = int(self.qty_input.value())
        
        try:
            service_info = self.price_summary_label.text()
            item_id = models.add_order_item(
                self.order_id, 
                description,
                service_info,
                qty, 
                total_price
            )
        except Exception as e:
            QMessageBox.critical(self, "Error adding item", str(e))
            return

        self.chk_laundry_coloured.setChecked(False)
        self.chk_laundry_white.setChecked(False)
        self.chk_pressing.setChecked(False)
        self.qty_input.setValue(1)
        
        self.refresh_order_snapshot()
        self.update_discount_suggestion()
        
        if self.express_checkbox.isChecked():
            self.express_amount = self.calculate_express_surcharge()
            self.update_totals_with_express()
        
        QMessageBox.information(
            self, 
            "Item added", 
            f"Added {qty} x {description}\nTotal: GH₵ {total_price * qty:.2f}"
        )

    def refresh_order_snapshot(self):
        if not self.order_id:
            return
        try:
            snap = models.get_order_with_items(self.order_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load order: {e}")
            return
        self.order_snapshot = snap
        
        items: List[Dict[str, Any]] = snap["items"]
        self.items_table.setRowCount(len(items))
        
        self.remove_item_combo.clear()
        
        for i, it in enumerate(items):
            self.items_table.setItem(i, 0, QTableWidgetItem(str(it.get("item_id", ""))))
            self.items_table.setItem(i, 1, QTableWidgetItem(str(it.get("item_type"))))
            self.items_table.setItem(i, 2, QTableWidgetItem(str(it.get("quantity"))))
            self.items_table.setItem(i, 3, QTableWidgetItem(fmt_money(float(it.get("unit_price") or 0.0)).replace("GH₵ ", "")))
            self.items_table.setItem(i, 4, QTableWidgetItem(fmt_money(float(it.get("subtotal") or 0.0)).replace("GH₵ ", "")))
            
            self.remove_item_combo.addItem(f"{it.get('item_type')} (ID: {it.get('item_id')})", it.get('item_id'))

        self.update_totals_with_express()

        order = snap["order"]
        if order:
            disc = float(order.get("discount") or 0.0)
            dtype = order.get("discount_type") or "fixed"
            self.discount_value.setValue(disc)
            if dtype == "percent":
                self.rb_percent.setChecked(True)
            else:
                self.rb_fixed.setChecked(True)

    def remove_selected_item(self):
        if not self.order_id or self.remove_item_combo.count() == 0:
            return
        
        item_id = self.remove_item_combo.currentData()
        if not item_id:
            return
        
        confirm = QMessageBox.question(
            self, "Confirm Remove", 
            f"Are you sure you want to remove this item?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            try:
                models.remove_order_item(self.order_id, item_id)
                self.refresh_order_snapshot()
                self.update_discount_suggestion()
                
                if self.express_checkbox.isChecked():
                    self.express_amount = self.calculate_express_surcharge()
                    if self.express_amount <= 0:
                        self.express_checkbox.setChecked(False)
                        self.express_active = False
                        self.express_amount = 0.0
                    self.update_totals_with_express()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to remove item: {e}")

    def apply_discount_clicked(self):
        if not self.order_id:
            QMessageBox.warning(self, "No order", "Create an order before applying discount.")
            return
        disc = float(self.discount_value.value() or 0.0)
        dtype = "percent" if self.rb_percent.isChecked() else "fixed"
        conn = database.connect_db()
        cur = conn.cursor()
        cur.execute("UPDATE orders SET discount = ?, discount_type = ? WHERE order_id = ?", (disc, dtype, self.order_id))
        conn.commit()
        conn.close()
        models.compute_order_totals(self.order_id)
        self.refresh_order_snapshot()
        QMessageBox.information(self, "Discount applied", f"Discount updated ({dtype} {disc}).")

    def finalize_order_clicked(self):
        if not self.order_id:
            QMessageBox.warning(self, "No order", "Create and add items to the order first.")
            return
        conn = database.connect_db()
        cur = conn.cursor()
        cur.execute("UPDATE orders SET status = ? WHERE order_id = ?", ("Received", self.order_id))
        conn.commit()
        conn.close()
        QMessageBox.information(self, "Order finalized", "Order finalized. You can now record payment or print invoice.")

    def print_invoice_clicked(self):
        if not self.order_id:
            QMessageBox.warning(self, "No order", "Create an order before printing invoice.")
            return
        try:
            import invoice
        except ImportError:
            QMessageBox.information(self, "Invoice not available", "Invoice module not found. Please ensure invoice.py exists.")
            return

        try:
            outfile = invoice.generate_invoice(self.order_id, open_file=False)
        except Exception as e:
            QMessageBox.critical(self, "Invoice error", f"Failed to generate invoice: {e}")
            return

        dlg = QMessageBox(self)
        dlg.setWindowTitle("Invoice Generated")
        dlg.setText(f"Invoice saved to:\n{outfile}\n\nWould you like to open the file or send it to the printer?")
        open_btn = dlg.addButton("Open", QMessageBox.AcceptRole)
        print_btn = dlg.addButton("Print", QMessageBox.ActionRole)
        close_btn = dlg.addButton("Close", QMessageBox.RejectRole)
        dlg.exec_()

        clicked = dlg.clickedButton()
        if clicked == open_btn:
            try:
                if os.name == "nt":
                    os.startfile(outfile)
                else:
                    webbrowser.open(str(outfile))
            except Exception as e:
                QMessageBox.warning(self, "Open failed", f"Could not open file: {e}")
        elif clicked == print_btn:
            confirm = QMessageBox.question(self, "Confirm Print", "Send invoice to default printer?", QMessageBox.Yes | QMessageBox.No)
            if confirm != QMessageBox.Yes:
                return
            try:
                if os.name == "nt":
                    os.startfile(outfile, "print")
                else:
                    QMessageBox.information(self, "Print not supported", "Automatic printing is only supported on Windows. Please open and print manually.")
            except Exception as e:
                QMessageBox.warning(self, "Print failed", f"Could not print file: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    admin = database.get_user_by_username("admin")
    w = OrdersWindow(current_user=admin)
    w.show()
    sys.exit(app.exec_())
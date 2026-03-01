#!/usr/bin/env python3
"""
reports.py

Updated Reports UI with export/print capabilities:
- Export daily orders to CSV
- Print (generate simple PDF) of daily report

Buttons added in the Daily Report area:
- Export CSV
- Print PDF

Printing/Export behavior:
- Export CSV writes a CSV with one row per order and columns:
    order_id, order_date, customer_name, status, total_amount, paid_amount, balance
- Print PDF generates a simple PDF report (summaries + table of orders) and opens it (or offers location)

Note: Report PDF generation uses reportlab (already in requirements).
"""

from typing import Optional, Dict, Any, List
import sys
import csv
import os
import datetime
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QGroupBox,
    QFormLayout,
    QDateEdit,
    QFileDialog,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QDate

import models
import database

# reportlab imports for PDF export
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

def fmt_money(v: float) -> str:
    return f"{v:,.2f}"


def export_daily_orders_csv(date_str: str, output_path: Optional[str] = None) -> str:
    """
    Export orders on a given date to CSV. Returns path to written file.
    If output_path is None, writes to reports_<date>.csv in current folder.
    """
    if not output_path:
        output_path = f"report_orders_{date_str}.csv"
    # Query orders with customer
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT o.order_id, o.order_date, o.status, o.total_amount, o.paid_amount, o.balance, c.name as customer_name
        FROM orders o LEFT JOIN customers c ON o.customer_id = c.customer_id
        WHERE DATE(o.order_date) = ?
        ORDER BY o.order_date ASC
        """,
        (date_str,),
    )
    rows = cur.fetchall()
    conn.close()
    # Write CSV
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["order_id", "order_date", "customer_name", "status", "total_amount", "paid_amount", "balance"])
        for r in rows:
            writer.writerow([r["order_id"], r["order_date"], r["customer_name"] or "", r["status"], f"{r['total_amount'] or 0:.2f}", f"{r['paid_amount'] or 0:.2f}", f"{r['balance'] or 0:.2f}"])
    return str(Path(output_path).absolute())


def print_daily_report_pdf(date_str: str, output_path: Optional[str] = None, open_file: bool = True) -> str:
    """
    Generate a printable PDF for the daily report. Returns file path.
    Requires reportlab. Creates a simple table of orders + summary.
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab is required for PDF generation. Install via 'pip install reportlab'")

    if not output_path:
        output_path = f"report_daily_{date_str}.pdf"

    # Fetch report summary and order rows
    summary = models.daily_report(date_str)
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT o.order_id, o.order_date, o.status, o.total_amount, o.paid_amount, o.balance, c.name as customer_name
        FROM orders o LEFT JOIN customers c ON o.customer_id = c.customer_id
        WHERE DATE(o.order_date) = ?
        ORDER BY o.order_date ASC
        """,
        (date_str,),
    )
    rows = cur.fetchall()
    conn.close()

    # Build PDF
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleCenter", parent=styles["Heading2"], alignment=1))
    elements = []
    elements.append(Paragraph(f"Daily Report — {date_str}", styles["TitleCenter"]))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f"Total Orders: {summary['total_orders']}", styles["Normal"]))
    elements.append(Paragraph(f"Total Sales: {fmt_money(summary['total_sales'])}", styles["Normal"]))
    elements.append(Paragraph(f"Total Paid: {fmt_money(summary['total_paid'])}", styles["Normal"]))
    elements.append(Paragraph(f"Outstanding: {fmt_money(summary['outstanding'])}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    # Table header + rows
    data = [["Order ID", "Order Date", "Customer", "Status", "Total", "Paid", "Balance"]]
    for r in rows:
        data.append([str(r["order_id"]), str(r["order_date"]), r["customer_name"] or "", r["status"], fmt_money(float(r["total_amount"] or 0.0)), fmt_money(float(r["paid_amount"] or 0.0)), fmt_money(float(r["balance"] or 0.0))])
    tbl = Table(data, colWidths=[22*mm, 32*mm, 50*mm, 28*mm, 22*mm, 22*mm, 22*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ("ALIGN", (4,1), (6,-1), "RIGHT"),
    ]))
    elements.append(tbl)
    doc.build(elements)

    if open_file:
        try:
            if os.name == "nt":
                os.startfile(output_path)
            else:
                import webbrowser
                webbrowser.open(output_path)
        except Exception:
            pass
    return str(Path(output_path).absolute())


class ReportsWindow(QWidget):
    STATUSES = ["Received", "Washed", "Ironed", "Ready", "Collected"]

    def __init__(self, current_user: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.current_user = current_user
        self.setWindowTitle("LMS — Status & Reports")
        self.setMinimumSize(1000, 640)
        self.selected_order_id: Optional[int] = None
        self._build_ui()
        self.load_orders_by_status("Received")

    def _build_ui(self):
        font_title = QFont("Segoe UI", 11, QFont.Bold)
        font = QFont("Segoe UI", 10)

        main = QHBoxLayout()

        # Left: Status filters and orders list
        left = QVBoxLayout()
        status_group = QGroupBox("Orders by Status")
        sg_layout = QVBoxLayout()
        for s in self.STATUSES:
            btn = QPushButton(s)
            btn.setFont(font)
            btn.clicked.connect(lambda checked, st=s: self.load_orders_by_status(st))
            sg_layout.addWidget(btn)
        status_group.setLayout(sg_layout)
        left.addWidget(status_group)

        orders_group = QGroupBox("Orders (click to select)")
        og_layout = QVBoxLayout()
        self.orders_list = QListWidget()
        self.orders_list.setFont(font)
        self.orders_list.itemClicked.connect(self._order_selected_from_list)
        og_layout.addWidget(self.orders_list)
        orders_group.setLayout(og_layout)
        left.addWidget(orders_group)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_current_list)
        left.addWidget(refresh_btn)
        left.addStretch(1)

        # Middle: Selected order details
        middle = QVBoxLayout()
        detail_group = QGroupBox("Selected Order Details")
        dg_layout = QFormLayout()
        self.lbl_order_id = QLabel("-")
        self.lbl_customer = QLabel("-")
        self.lbl_order_date = QLabel("-")
        self.lbl_status = QLabel("-")
        self.lbl_special = QLabel("-")
        for lbl in (self.lbl_order_id, self.lbl_customer, self.lbl_order_date, self.lbl_status, self.lbl_special):
            lbl.setFont(font)
        dg_layout.addRow("Order ID:", self.lbl_order_id)
        dg_layout.addRow("Customer:", self.lbl_customer)
        dg_layout.addRow("Order Date:", self.lbl_order_date)
        dg_layout.addRow("Status:", self.lbl_status)
        dg_layout.addRow("Special:", self.lbl_special)
        detail_group.setLayout(dg_layout)
        middle.addWidget(detail_group)

        self.items_table = QTableWidget()
        self.items_table.setColumnCount(5)
        self.items_table.setHorizontalHeaderLabels(["Item", "Color", "Qty", "Unit Price", "Subtotal"])
        self.items_table.setEditTriggers(QTableWidget.NoEditTriggers)
        middle.addWidget(self.items_table)

        totals_group = QGroupBox("Totals")
        totals_layout = QFormLayout()
        self.t_subtotal = QLabel("0.00")
        self.t_discount = QLabel("0.00")
        self.t_total = QLabel("0.00")
        self.t_paid = QLabel("0.00")
        self.t_balance = QLabel("0.00")
        for lbl in (self.t_subtotal, self.t_discount, self.t_total, self.t_paid, self.t_balance):
            lbl.setFont(font)
            lbl.setAlignment(Qt.AlignRight)
        totals_layout.addRow("Subtotal:", self.t_subtotal)
        totals_layout.addRow("Discount:", self.t_discount)
        totals_layout.addRow("Total:", self.t_total)
        totals_layout.addRow("Paid:", self.t_paid)
        totals_layout.addRow("Balance:", self.t_balance)
        totals_group.setLayout(totals_layout)
        middle.addWidget(totals_group)
        middle.addStretch(1)

        # Right: Actions & Reports (with export/print)
        right = QVBoxLayout()
        actions_group = QGroupBox("Update Status")
        act_layout = QVBoxLayout()
        for s in self.STATUSES:
            b = QPushButton(f"Mark as {s}")
            b.clicked.connect(lambda checked, st=s: self.change_status_clicked(st))
            b.setFont(font)
            act_layout.addWidget(b)
        actions_group.setLayout(act_layout)
        right.addWidget(actions_group)

        report_group = QGroupBox("Daily Report")
        rg_layout = QFormLayout()
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        rg_layout.addRow("Date:", self.date_edit)
        run_btn = QPushButton("Run Daily Report")
        run_btn.clicked.connect(self.run_daily_report)
        rg_layout.addRow("", run_btn)

        # Export & Print buttons
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self.export_csv_clicked)
        print_btn = QPushButton("Print PDF")
        print_btn.clicked.connect(self.print_pdf_clicked)
        rg_layout.addRow("", export_btn)
        rg_layout.addRow("", print_btn)

        # Results
        self.r_total_orders = QLabel("-")
        self.r_total_sales = QLabel("-")
        self.r_total_paid = QLabel("-")
        self.r_outstanding = QLabel("-")
        for lbl in (self.r_total_orders, self.r_total_sales, self.r_total_paid, self.r_outstanding):
            lbl.setFont(font)
            lbl.setAlignment(Qt.AlignRight)
        rg_layout.addRow("Total Orders:", self.r_total_orders)
        rg_layout.addRow("Total Sales:", self.r_total_sales)
        rg_layout.addRow("Total Paid:", self.r_total_paid)
        rg_layout.addRow("Outstanding:", self.r_outstanding)

        report_group.setLayout(rg_layout)
        right.addWidget(report_group)
        right.addStretch(1)

        main.addLayout(left, stretch=3)
        main.addLayout(middle, stretch=5)
        main.addLayout(right, stretch=3)
        self.setLayout(main)

    # Methods (same as previous implementation)...
    def load_orders_by_status(self, status: str):
        self.current_status_filter = status
        self.orders_list.clear()
        try:
            rows = models.list_orders_by_status(status)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load orders by status: {e}")
            return
        if not rows:
            self.orders_list.addItem("No orders found.")
            return
        for r in rows:
            cust = "(unknown)"
            try:
                conn = database.connect_db()
                cur = conn.cursor()
                cur.execute("SELECT name FROM customers WHERE customer_id = ?", (r["customer_id"],))
                crow = cur.fetchone()
                conn.close()
                if crow:
                    cust = crow["name"]
            except Exception:
                pass
            display = f"{r['order_id']}  -  {cust}  -  {str(r['order_date']).split(' ')[0]}  -  {fmt_money(float(r.get('total_amount') or 0.0))}"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, r)
            self.orders_list.addItem(item)

    def _order_selected_from_list(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        if not data:
            return
        order_id = int(data["order_id"])
        self.select_order(order_id)

    def _refresh_current_list(self):
        st = getattr(self, "current_status_filter", "Received")
        self.load_orders_by_status(st)

    def select_order(self, order_id: int):
        try:
            snap = models.get_order_with_items(order_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load order {order_id}: {e}")
            return
        self.selected_order_id = order_id
        order = snap["order"]
        customer = snap.get("customer") or {}
        items = snap.get("items") or []
        payments = snap.get("payments") or []

        self.lbl_order_id.setText(str(order.get("order_id")))
        self.lbl_customer.setText(f"{customer.get('name') or 'Unknown'} ({customer.get('phone') or ''})")
        self.lbl_order_date.setText(str(order.get("order_date") or ""))
        self.lbl_status.setText(str(order.get("status") or ""))
        self.lbl_special.setText(str(order.get("special_instructions") or ""))

        self.items_table.setRowCount(len(items))
        for i, it in enumerate(items):
            self.items_table.setItem(i, 0, QTableWidgetItem(str(it.get("item_type") or "")))
            self.items_table.setItem(i, 1, QTableWidgetItem(str(it.get("color_category") or "")))
            self.items_table.setItem(i, 2, QTableWidgetItem(str(it.get("quantity") or 0)))
            self.items_table.setItem(i, 3, QTableWidgetItem(fmt_money(float(it.get("unit_price") or 0.0))))
            self.items_table.setItem(i, 4, QTableWidgetItem(fmt_money(float(it.get("subtotal") or 0.0))))

        totals = models.compute_order_totals(order_id)
        self.t_subtotal.setText(fmt_money(totals["subtotal"]))
        self.t_discount.setText(fmt_money(totals["discount_amount"]))
        self.t_total.setText(fmt_money(totals["total_amount"]))
        self.t_paid.setText(fmt_money(totals["paid_amount"]))
        self.t_balance.setText(fmt_money(totals["balance"]))

    def change_status_clicked(self, new_status: str):
        if not self.selected_order_id:
            QMessageBox.warning(self, "No order selected", "Select an order to update its status.")
            return
        confirm = QMessageBox.question(self, "Confirm status change", f"Mark order {self.selected_order_id} as '{new_status}'?", QMessageBox.Yes | QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        try:
            conn = database.connect_db()
            cur = conn.cursor()
            cur.execute("UPDATE orders SET status = ? WHERE order_id = ?", (new_status, self.selected_order_id))
            conn.commit()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Update failed", f"Failed to update status: {e}")
            return
        QMessageBox.information(self, "Status updated", f"Order {self.selected_order_id} marked as '{new_status}'.")
        self.select_order(self.selected_order_id)
        self._refresh_current_list()

    def run_daily_report(self):
        qdate = self.date_edit.date().toString("yyyy-MM-dd")
        try:
            rep = models.daily_report(qdate)
        except Exception as e:
            QMessageBox.critical(self, "Report error", f"Failed to run daily report: {e}")
            return
        self.r_total_orders.setText(str(rep["total_orders"]))
        self.r_total_sales.setText(fmt_money(float(rep["total_sales"])))
        self.r_total_paid.setText(fmt_money(float(rep["total_paid"])))
        self.r_outstanding.setText(fmt_money(float(rep["outstanding"])))

    def export_csv_clicked(self):
        qdate = self.date_edit.date().toString("yyyy-MM-dd")
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", f"report_orders_{qdate}.csv", "CSV files (*.csv)")
        if not path:
            return
        try:
            out = export_daily_orders_csv(qdate, path)
            QMessageBox.information(self, "Exported", f"CSV exported to: {out}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", f"Failed to export CSV: {e}")

    def print_pdf_clicked(self):
        if not REPORTLAB_AVAILABLE:
            QMessageBox.warning(self, "reportlab required", "PDF printing requires reportlab. Install with 'pip install reportlab'")
            return
        qdate = self.date_edit.date().toString("yyyy-MM-dd")
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF Report", f"report_daily_{qdate}.pdf", "PDF files (*.pdf)")
        if not path:
            return
        try:
            out = print_daily_report_pdf(qdate, path, open_file=True)
            QMessageBox.information(self, "Printed", f"Report PDF created: {out}")
        except Exception as e:
            QMessageBox.critical(self, "Print failed", f"Failed to create/print PDF: {e}")


# Standalone runner for quick testing
def main():
    app = QApplication(sys.argv)
    admin = database.get_user_by_username("admin")
    win = ReportsWindow(current_user=admin)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
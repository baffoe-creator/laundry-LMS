#!/usr/bin/env python3
"""
reports.py

Updated Reports UI with export/print capabilities:
- Export daily orders to CSV
- Print (generate simple PDF) of daily report
- Period Report (date range) with summary and details
- Export period orders to CSV
- Print period report PDF with summary and details

Fixes/Updates:
- Fixed PDF formatting to match invoice style
- Fixed GH₵ symbol display using DejaVuSans font
- Fixed company header to properly load from config.json
- Improved layout to reduce excessive scrolling
"""

from typing import Optional, Dict, Any, List
import sys
import csv
import os
import json
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
    QScrollArea,
    QSizePolicy,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QDate

import models
import database

# reportlab imports for PDF export
try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
    
    # Register DejaVuSans for GH₵ symbol support
    font_path = os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans.ttf")
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
        pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans-Bold.ttf")))
        FONT_NAME = 'DejaVuSans'
        FONT_BOLD = 'DejaVuSans-Bold'
    else:
        # Fallback to Helvetica if DejaVu not available
        FONT_NAME = 'Helvetica'
        FONT_BOLD = 'Helvetica-Bold'
        print("Warning: DejaVuSans not found, using Helvetica (GH₵ may not display correctly)")
        
except Exception as e:
    print(f"ReportLab import error: {e}")
    REPORTLAB_AVAILABLE = False

def fmt_money(v: float) -> str:
    """Format money with GH₵ symbol - using unicode character directly"""
    return f"GH₵ {v:,.2f}"

def fmt_money_pdf(v: float) -> str:
    """Format money for PDF with proper symbol handling"""
    try:
        if FONT_NAME == 'DejaVuSans':
            return f"₵ {v:,.2f}"
        else:
            return f"GHS {v:,.2f}"
    except NameError:
        return f"GHS {v:,.2f}"

def load_company_info() -> Dict[str, str]:
    """Load company info from config.json for PDF headers."""
    try:
        with open("config.json", "r", encoding='utf-8') as f:
            data = json.load(f)
            # Handle nested company structure
            if "company" in data:
                return data["company"]
            return data
    except:
        return {
            "name": "NII ET AL Laundry",
            "address": "Teseano Gardens Flint Street Next to Ginell Gift Shop. P.O.Box 2906, Accra",
            "phone": "0248375710 / 0277551309",
            "email": "niietalgh@gmail.com"
        }


def export_daily_orders_csv(date_str: str, output_path: Optional[str] = None) -> str:
    """Export orders on a given date to CSV."""
    if not output_path:
        output_path = f"report_orders_{date_str}.csv"
    
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
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["order_id", "order_date", "customer_name", "status", "total_amount", "paid_amount", "balance"])
        for r in rows:
            writer.writerow([r["order_id"], r["order_date"], r["customer_name"] or "", r["status"], 
                           f"{r['total_amount'] or 0:.2f}", f"{r['paid_amount'] or 0:.2f}", f"{r['balance'] or 0:.2f}"])
    return str(Path(output_path).absolute())


def export_range_orders_csv(date_from: str, date_to: str, output_path: Optional[str] = None) -> str:
    """Export all orders in [date_from, date_to] to CSV."""
    if not output_path:
        output_path = f"report_orders_{date_from}_to_{date_to}.csv"
    
    orders = models.list_orders_in_range(date_from, date_to)
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["order_id", "order_date", "customer_name", "customer_phone", "status", 
                        "total_amount", "paid_amount", "balance"])
        for o in orders:
            writer.writerow([
                o["order_id"], 
                o["order_date"], 
                o.get("customer_name", ""),
                o.get("customer_phone", ""),
                o["status"],
                f"{o['total_amount']:.2f}", 
                f"{o['paid_amount']:.2f}", 
                f"{o['balance']:.2f}"
            ])
    return str(Path(output_path).absolute())


def print_daily_report_pdf(date_str: str, output_path: Optional[str] = None, open_file: bool = True) -> str:
    """
    Generate a printable PDF for the daily report matching invoice style.
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab is required for PDF generation. Install via 'pip install reportlab'")

    if not output_path:
        output_path = f"report_daily_{date_str}.pdf"

    summary = models.daily_report(date_str)
    orders = models.list_orders_in_range(date_str, date_str)
    company = load_company_info()

    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, 
                           topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    
    # Use registered font if available
    font_name = FONT_NAME if 'FONT_NAME' in globals() else 'Helvetica'
    font_bold = FONT_BOLD if 'FONT_BOLD' in globals() else 'Helvetica-Bold'
    
    # Custom styles matching invoice
    styles.add(ParagraphStyle(name="CompanyName", 
                              parent=styles["Normal"],
                              fontName=font_bold,
                              fontSize=14,
                              alignment=1,  # Center
                              spaceAfter=4))
    
    styles.add(ParagraphStyle(name="CompanyDetails",
                              parent=styles["Normal"],
                              fontName=font_name,
                              fontSize=9,
                              alignment=1,
                              textColor=colors.HexColor("#666666"),
                              spaceAfter=2))
    
    styles.add(ParagraphStyle(name="ReportTitle",
                              parent=styles["Normal"],
                              fontName=font_bold,
                              fontSize=12,
                              alignment=1,
                              spaceAfter=12))
    
    styles.add(ParagraphStyle(name="SectionHeader",
                              parent=styles["Normal"],
                              fontName=font_bold,
                              fontSize=11,
                              spaceAfter=6))
    
    elements = []
    
    # Company Header (matching invoice style)
    elements.append(Paragraph(company.get("name", "LMS"), styles["CompanyName"]))
    if company.get("address"):
        elements.append(Paragraph(company["address"], styles["CompanyDetails"]))
    if company.get("phone") or company.get("email"):
        elements.append(Paragraph(f"Tel: {company.get('phone', '')}  Email: {company.get('email', '')}", styles["CompanyDetails"]))
    elements.append(Spacer(1, 8))
    
    # Report Title
    elements.append(Paragraph(f"Daily Sales Report — {date_str}", styles["ReportTitle"]))
    elements.append(Spacer(1, 8))

    # Summary in a table for better formatting
    summary_data = [
        ["Total Orders:", str(summary['total_orders']), "", ""],
        ["Total Sales:", fmt_money_pdf(summary['total_sales']), "Total Paid:", fmt_money_pdf(summary['total_paid'])],
        ["Outstanding:", fmt_money_pdf(summary['outstanding']), "", ""]
    ]
    
    summary_table = Table(summary_data, colWidths=[40*mm, 40*mm, 40*mm, 40*mm])
    summary_table.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("ALIGN", (3,1), (3,1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LINEBELOW", (0,0), (-1,0), 0.5, colors.grey),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 12))

    # Orders table
    elements.append(Paragraph("Order Details", styles["SectionHeader"]))
    elements.append(Spacer(1, 4))
    
    data = [["Order ID", "Date", "Customer", "Status", "Total", "Paid", "Balance"]]
    for o in orders:
        order_date = str(o["order_date"]).split(" ")[0]
        data.append([
            str(o["order_id"]), 
            order_date,
            o.get("customer_name", "") or "",
            o["status"], 
            fmt_money_pdf(float(o["total_amount"] or 0.0)), 
            fmt_money_pdf(float(o["paid_amount"] or 0.0)), 
            fmt_money_pdf(float(o["balance"] or 0.0))
        ])
    
    tbl = Table(data, colWidths=[18*mm, 22*mm, 50*mm, 22*mm, 22*mm, 22*mm, 22*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1A3C5E")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONT", (0,0), (-1,0), font_bold),
        ("FONT", (0,1), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,0), 9),
        ("FONTSIZE", (0,1), (-1,-1), 8),
        ("ALIGN", (4,1), (6,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f9f9f9")]),
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


def print_range_report_pdf(date_from: str, date_to: str, output_path: Optional[str] = None, 
                          open_file: bool = True) -> str:
    """
    Generate a PDF covering the date range matching invoice style.
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab is required for PDF generation. Install via 'pip install reportlab'")

    if not output_path:
        output_path = f"report_period_{date_from}_to_{date_to}.pdf"

    report_data = models.range_report(date_from, date_to)
    orders = models.list_orders_in_range(date_from, date_to)
    company = load_company_info()

    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, 
                           topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    
    # Use registered font if available
    font_name = FONT_NAME if 'FONT_NAME' in globals() else 'Helvetica'
    font_bold = FONT_BOLD if 'FONT_BOLD' in globals() else 'Helvetica-Bold'
    
    # Custom styles matching invoice
    styles.add(ParagraphStyle(name="CompanyName", 
                              parent=styles["Normal"],
                              fontName=font_bold,
                              fontSize=14,
                              alignment=1,
                              spaceAfter=4))
    
    styles.add(ParagraphStyle(name="CompanyDetails",
                              parent=styles["Normal"],
                              fontName=font_name,
                              fontSize=9,
                              alignment=1,
                              textColor=colors.HexColor("#666666"),
                              spaceAfter=2))
    
    styles.add(ParagraphStyle(name="ReportTitle",
                              parent=styles["Normal"],
                              fontName=font_bold,
                              fontSize=12,
                              alignment=1,
                              spaceAfter=12))
    
    styles.add(ParagraphStyle(name="SectionHeader",
                              parent=styles["Normal"],
                              fontName=font_bold,
                              fontSize=11,
                              spaceAfter=6))
    
    styles.add(ParagraphStyle(name="SubHeader",
                              parent=styles["Normal"],
                              fontName=font_bold,
                              fontSize=10,
                              spaceAfter=4))
    
    elements = []
    
    # Company Header (matching invoice style)
    elements.append(Paragraph(company.get("name", "LMS"), styles["CompanyName"]))
    if company.get("address"):
        elements.append(Paragraph(company["address"], styles["CompanyDetails"]))
    if company.get("phone") or company.get("email"):
        elements.append(Paragraph(f"Tel: {company.get('phone', '')}  Email: {company.get('email', '')}", styles["CompanyDetails"]))
    elements.append(Spacer(1, 8))
    
    # Report Title
    elements.append(Paragraph(f"Period Sales Report: {date_from} to {date_to}", styles["ReportTitle"]))
    elements.append(Spacer(1, 12))

    # Summary section
    elements.append(Paragraph("Summary", styles["SectionHeader"]))
    elements.append(Spacer(1, 4))
    
    summary_data = [
        ["Total Orders:", str(report_data['total_orders']), "", ""],
        ["Total Sales:", fmt_money_pdf(report_data['total_sales']), "Total Paid:", fmt_money_pdf(report_data['total_paid'])],
        ["Outstanding:", fmt_money_pdf(report_data['outstanding']), "", ""]
    ]
    
    summary_table = Table(summary_data, colWidths=[40*mm, 40*mm, 40*mm, 40*mm])
    summary_table.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("ALIGN", (3,1), (3,1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LINEBELOW", (0,0), (-1,0), 0.5, colors.grey),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 12))

    # Orders by Status
    if report_data['orders_by_status']:
        elements.append(Paragraph("Orders by Status", styles["SubHeader"]))
        status_data = [["Status", "Count"]]
        for status, count in report_data['orders_by_status'].items():
            status_data.append([status, str(count)])
        status_tbl = Table(status_data, colWidths=[80*mm, 30*mm])
        status_tbl.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1A3C5E")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONT", (0,0), (-1,0), font_bold),
            ("FONT", (0,1), (-1,-1), font_name),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ]))
        elements.append(status_tbl)
        elements.append(Spacer(1, 8))

    # Daily Breakdown
    if report_data['daily_breakdown']:
        elements.append(Paragraph("Daily Breakdown", styles["SubHeader"]))
        daily_data = [["Date", "Orders", "Sales", "Paid", "Outstanding"]]
        for day in report_data['daily_breakdown']:
            daily_data.append([
                day['date'],
                str(day['order_count']),
                fmt_money_pdf(day['sales']),
                fmt_money_pdf(day['paid']),
                fmt_money_pdf(day['outstanding'])
            ])
        daily_tbl = Table(daily_data, colWidths=[30*mm, 20*mm, 30*mm, 30*mm, 30*mm])
        daily_tbl.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1A3C5E")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONT", (0,0), (-1,0), font_bold),
            ("FONT", (0,1), (-1,-1), font_name),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("ALIGN", (2,1), (4,-1), "RIGHT"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ]))
        elements.append(daily_tbl)
    
    elements.append(PageBreak())
    
    # Detail section - Orders table
    elements.append(Paragraph("Order Details", styles["SectionHeader"]))
    elements.append(Spacer(1, 4))
    
    data = [["Order ID", "Date", "Customer", "Status", "Total", "Paid", "Balance"]]
    for o in orders:
        order_date = str(o["order_date"]).split(" ")[0]
        data.append([
            str(o["order_id"]), 
            order_date,
            o.get("customer_name", "") or "",
            o["status"], 
            fmt_money_pdf(float(o["total_amount"] or 0.0)), 
            fmt_money_pdf(float(o["paid_amount"] or 0.0)), 
            fmt_money_pdf(float(o["balance"] or 0.0))
        ])
    
    tbl = Table(data, colWidths=[18*mm, 22*mm, 50*mm, 22*mm, 22*mm, 22*mm, 22*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1A3C5E")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONT", (0,0), (-1,0), font_bold),
        ("FONT", (0,1), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,0), 9),
        ("FONTSIZE", (0,1), (-1,-1), 8),
        ("ALIGN", (4,1), (6,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f9f9f9")]),
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


def _make_scrollable(widget: QWidget, min_width: int = 0) -> QScrollArea:
    """Wrap a widget in a scroll area with smarter sizing."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setWidget(widget)
    if min_width > 0:
        scroll.setMinimumWidth(min_width)
    return scroll


class ReportsWindow(QWidget):
    STATUSES = ["Received", "Washed", "Ironed", "Ready", "Collected"]

    def __init__(self, current_user: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.current_user = current_user
        self.setWindowTitle("LMS — Status & Reports")
        self.setMinimumSize(1000, 600)
        self.selected_order_id: Optional[int] = None
        self._build_ui()
        self.load_orders_by_status("Received")

    def _build_ui(self):
        font = QFont("Segoe UI", 10)

        main = QHBoxLayout()
        main.setSpacing(8)
        main.setContentsMargins(8, 8, 8, 8)

        # Left: Status filters and orders list
        left_container = QWidget()
        left = QVBoxLayout(left_container)
        left.setContentsMargins(0, 0, 0, 0)
        
        status_group = QGroupBox("Orders by Status")
        sg_layout = QVBoxLayout()
        self.status_buttons = []
        for i, s in enumerate(self.STATUSES):
            btn = QPushButton(s)
            btn.setFont(font)
            btn.setObjectName("statusBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            if i == 0:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, st=s: self.load_orders_by_status(st))
            sg_layout.addWidget(btn)
            self.status_buttons.append(btn)
        status_group.setLayout(sg_layout)
        left.addWidget(status_group)

        orders_group = QGroupBox("Orders (click to select)")
        orders_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        og_layout = QVBoxLayout()
        self.orders_list = QListWidget()
        self.orders_list.setFont(font)
        self.orders_list.setObjectName("recentList")
        self.orders_list.itemClicked.connect(self._order_selected_from_list)
        og_layout.addWidget(self.orders_list)
        orders_group.setLayout(og_layout)
        left.addWidget(orders_group)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_current_list)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        left.addWidget(refresh_btn)

        # Middle: Selected order details
        middle_container = QWidget()
        middle = QVBoxLayout(middle_container)
        middle.setContentsMargins(0, 0, 0, 0)
        
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
        self.items_table.setAlternatingRowColors(True)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.horizontalHeader().setStretchLastSection(True)
        self.items_table.setMinimumHeight(150)
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

        # Right: Actions & Reports
        right_container = QWidget()
        right = QVBoxLayout(right_container)
        right.setContentsMargins(0, 0, 0, 0)

        actions_group = QGroupBox("Update Status")
        act_layout = QVBoxLayout()
        for s in self.STATUSES:
            b = QPushButton(f"Mark as {s}")
            b.clicked.connect(lambda checked, st=s: self.change_status_clicked(st))
            b.setFont(font)
            b.setCursor(Qt.PointingHandCursor)
            act_layout.addWidget(b)
        actions_group.setLayout(act_layout)
        right.addWidget(actions_group)

        # Daily Report group
        daily_group = QGroupBox("Daily Report")
        dg_layout = QFormLayout()
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        dg_layout.addRow("Date:", self.date_edit)
        run_btn = QPushButton("Run Daily Report")
        run_btn.clicked.connect(self.run_daily_report)
        run_btn.setCursor(Qt.PointingHandCursor)
        dg_layout.addRow("", run_btn)

        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self.export_csv_clicked)
        export_btn.setCursor(Qt.PointingHandCursor)
        print_btn = QPushButton("Print PDF")
        print_btn.clicked.connect(self.print_pdf_clicked)
        print_btn.setCursor(Qt.PointingHandCursor)
        dg_layout.addRow("", export_btn)
        dg_layout.addRow("", print_btn)

        self.r_total_orders = QLabel("-")
        self.r_total_sales = QLabel("-")
        self.r_total_paid = QLabel("-")
        self.r_outstanding = QLabel("-")
        for lbl in (self.r_total_orders, self.r_total_sales, self.r_total_paid, self.r_outstanding):
            lbl.setFont(font)
            lbl.setAlignment(Qt.AlignRight)
        dg_layout.addRow("Total Orders:", self.r_total_orders)
        dg_layout.addRow("Total Sales:", self.r_total_sales)
        dg_layout.addRow("Total Paid:", self.r_total_paid)
        dg_layout.addRow("Outstanding:", self.r_outstanding)

        daily_group.setLayout(dg_layout)
        right.addWidget(daily_group)

        # Period Report group
        period_group = QGroupBox("Period Report")
        pg_layout = QFormLayout()
        
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        first_of_month = QDate.currentDate()
        first_of_month = first_of_month.addDays(-first_of_month.day() + 1)
        self.from_date.setDate(first_of_month)
        pg_layout.addRow("From:", self.from_date)
        
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDate(QDate.currentDate())
        pg_layout.addRow("To:", self.to_date)
        
        run_period_btn = QPushButton("Run Period Report")
        run_period_btn.clicked.connect(self.run_period_report)
        run_period_btn.setCursor(Qt.PointingHandCursor)
        run_period_btn.setProperty("accent", True)
        pg_layout.addRow("", run_period_btn)
        
        self.p_total_orders = QLabel("-")
        self.p_total_sales = QLabel("-")
        self.p_total_paid = QLabel("-")
        self.p_outstanding = QLabel("-")
        self.p_status_breakdown = QLabel("-")
        self.p_status_breakdown.setWordWrap(True)
        
        for lbl in (self.p_total_orders, self.p_total_sales, self.p_total_paid, self.p_outstanding):
            lbl.setFont(font)
            lbl.setAlignment(Qt.AlignRight)
        
        pg_layout.addRow("Total Orders:", self.p_total_orders)
        pg_layout.addRow("Total Sales:", self.p_total_sales)
        pg_layout.addRow("Total Paid:", self.p_total_paid)
        pg_layout.addRow("Outstanding:", self.p_outstanding)
        pg_layout.addRow("Status:", self.p_status_breakdown)
        
        export_period_btn = QPushButton("Export CSV (Period)")
        export_period_btn.clicked.connect(self.export_period_csv_clicked)
        export_period_btn.setCursor(Qt.PointingHandCursor)
        print_period_btn = QPushButton("Print PDF (Period)")
        print_period_btn.clicked.connect(self.print_period_pdf_clicked)
        print_period_btn.setCursor(Qt.PointingHandCursor)
        pg_layout.addRow("", export_period_btn)
        pg_layout.addRow("", print_period_btn)
        
        period_group.setLayout(pg_layout)
        right.addWidget(period_group)

        # Wrap columns that need scrolling
        left_scroll = _make_scrollable(left_container, 200)
        middle_scroll = _make_scrollable(middle_container, 320)
        right_scroll = _make_scrollable(right_container, 250)

        main.addWidget(left_scroll, stretch=2)
        main.addWidget(middle_scroll, stretch=4)
        main.addWidget(right_scroll, stretch=3)
        self.setLayout(main)

    def load_orders_by_status(self, status: str):
        # Update button states
        for btn in self.status_buttons:
            btn.setChecked(btn.text() == status)
        
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

    def run_period_report(self):
        from_date = self.from_date.date().toString("yyyy-MM-dd")
        to_date = self.to_date.date().toString("yyyy-MM-dd")
        
        if from_date > to_date:
            QMessageBox.warning(self, "Invalid Range", "From date must not be after To date.")
            return
        
        from_dt = QDate.fromString(from_date, "yyyy-MM-dd")
        to_dt = QDate.fromString(to_date, "yyyy-MM-dd")
        days_diff = from_dt.daysTo(to_dt)
        
        if days_diff > 366:
            confirm = QMessageBox.question(
                self, "Large Date Range",
                f"This range spans {days_diff} days, which may be slow. Continue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return
        
        try:
            rep = models.range_report(from_date, to_date)
        except Exception as e:
            QMessageBox.critical(self, "Report error", f"Failed to run period report: {e}")
            return
        
        self.p_total_orders.setText(str(rep["total_orders"]))
        self.p_total_sales.setText(fmt_money(rep["total_sales"]))
        self.p_total_paid.setText(fmt_money(rep["total_paid"]))
        self.p_outstanding.setText(fmt_money(rep["outstanding"]))
        
        status_text = " | ".join([f"{k}: {v}" for k, v in rep["orders_by_status"].items()])
        self.p_status_breakdown.setText(status_text if status_text else "None")

    def export_period_csv_clicked(self):
        from_date = self.from_date.date().toString("yyyy-MM-dd")
        to_date = self.to_date.date().toString("yyyy-MM-dd")
        
        if from_date > to_date:
            QMessageBox.warning(self, "Invalid Range", "From date must not be after To date.")
            return
        
        default_name = f"report_orders_{from_date}_to_{to_date}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export Period CSV", default_name, "CSV files (*.csv)")
        if not path:
            return
        
        try:
            out = export_range_orders_csv(from_date, to_date, path)
            QMessageBox.information(self, "Exported", f"CSV exported to: {out}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", f"Failed to export CSV: {e}")

    def print_period_pdf_clicked(self):
        if not REPORTLAB_AVAILABLE:
            QMessageBox.warning(self, "reportlab required", "PDF printing requires reportlab. Install with 'pip install reportlab'")
            return
        
        from_date = self.from_date.date().toString("yyyy-MM-dd")
        to_date = self.to_date.date().toString("yyyy-MM-dd")
        
        if from_date > to_date:
            QMessageBox.warning(self, "Invalid Range", "From date must not be after To date.")
            return
        
        default_name = f"report_period_{from_date}_to_{to_date}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Save Period PDF", default_name, "PDF files (*.pdf)")
        if not path:
            return
        
        try:
            out = print_range_report_pdf(from_date, to_date, path, open_file=True)
            QMessageBox.information(self, "Printed", f"Period report PDF created: {out}")
        except Exception as e:
            QMessageBox.critical(self, "Print failed", f"Failed to create/print PDF: {e}")


def main():
    app = QApplication(sys.argv)
    admin = database.get_user_by_username("admin")
    win = ReportsWindow(current_user=admin)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
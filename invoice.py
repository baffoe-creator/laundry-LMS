#!/usr/bin/env python3
"""
invoice.py

This generates PDF invoices with:
- Logo/header image support
- Express charge calculation and display
- Disclaimer footer
- Company info from settings.get_company_info()
"""

from pathlib import Path
import os
import sys
import datetime
import webbrowser
from typing import Optional, Dict, Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)
from reportlab.pdfgen import canvas

import models
import database

try:
    import settings as settings_module
except Exception:
    settings_module = None

DEFAULT_COMPANY = {
    "name": "NII ET AL Laundry",
    "address": "123 Laundry Lane\nCity, Country",
    "phone": "0700-000-000",
    "email": "info@niietallaundry.example",
    "footer_note": "Thank you for your business!",
}

INVOICE_DIR = Path("invoices")
INVOICE_DIR.mkdir(parents=True, exist_ok=True)

DISCLAIMER_TEXT = """
PICK UP & DELIVERY SERVICE ALSO AVAILABLE

CAUTION: CUSTOMER SHOULD PLEASE TAKE NOTE
(1) - Allowable laundry pick up time is a minimum of three (3) days and maximum of a week from date of delivery by customer, any exception will attract an extra fee (5GHS) Per every week of delay in pick up (unless communicated or notified)
(2) - The company will not be responsible for any item left in our care for more than two weeks, if it gets misplaced
(3) - Management will not be responsible for the loss of items (e.g. money) left in the customers pocket
(4) - If any item has been lost or damaged by our negligence, our compensation is limited to 10 times of laundry charge.
(5) - No liability can be accepted for damage which is due to manufacture or deterioration by wear and tear exposure
(6) - Foreign material object left in the customer pockets which causes any form of injury to staff will be surcharge as a liability to the customer
(7) - For dissatisfaction of service of any kind, kindly make a formal complain. Your feedback is always appreciated.
"""


def _fmt_money(v: float) -> str:
    return f"{v:,.2f}"


def _build_order_table_data(items: list, styles) -> list:
    header = ["#", "Item", "Color", "Qty", "Unit Price", "Subtotal"]
    data = [header]
    for i, it in enumerate(items, start=1):
        item_name = Paragraph(str(it.get("item_type") or ""), styles["NormalLeft"])
        color = Paragraph(str(it.get("color_category") or ""), styles["NormalLeft"])
        qty = str(it.get("quantity") or 0)
        unit = _fmt_money(float(it.get("unit_price") or 0.0))
        subtotal = _fmt_money(float(it.get("subtotal") or 0.0))
        data.append([str(i), item_name, color, qty, unit, subtotal])
    return data


def _add_page_number(canvas_obj: canvas.Canvas, doc):
    page_num = canvas_obj.getPageNumber()
    text = f"Page {page_num}"
    canvas_obj.setFont("Helvetica", 8)
    width, height = A4
    canvas_obj.drawRightString(width - 15 * mm, 10 * mm, text)


def generate_invoice(
    order_id: int,
    output_path: Optional[str] = None,
    company_info: Optional[Dict[str, str]] = None,
    open_file: bool = True,
) -> str:
    if company_info is None and settings_module is not None:
        try:
            company_info = settings_module.get_company_info()
        except Exception:
            company_info = DEFAULT_COMPANY.copy()
    company = company_info or DEFAULT_COMPANY.copy()

    snapshot = models.get_order_with_items(order_id)
    order = snapshot["order"]
    customer = snapshot.get("customer") or {}
    items = snapshot.get("items") or []
    payments = snapshot.get("payments") or []

    totals = models.compute_order_totals(order_id)
    subtotal = totals["subtotal"]
    express_charge = totals.get("express_charge", 0.0)
    discount_amount = totals["discount_amount"]
    total_amount = totals["total_amount"]
    paid_amount = totals["paid_amount"]
    balance = totals["balance"]

    invoice_no = models.format_invoice_number(order_id, order.get("order_date"))

    if output_path:
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_path = INVOICE_DIR / f"invoice_{invoice_no}.pdf"

    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                            rightMargin=15 * mm, leftMargin=15 * mm, topMargin=18 * mm, bottomMargin=25 * mm)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="InvoiceTitle", fontSize=16, leading=20, alignment=1))
    styles.add(ParagraphStyle(name="NormalLeft", parent=styles["Normal"], alignment=0, leading=12))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="MetaLabel", parent=styles["Normal"], fontSize=9, leading=12))
    styles.add(ParagraphStyle(name="MetaValue", parent=styles["Normal"], fontSize=10, leading=12))
    styles.add(ParagraphStyle(name="Disclaimer", parent=styles["Normal"], fontSize=7, leading=9))

    elements = []

    logo_path = company.get("logo_path", "") or ""
    logo_width = 40 * mm
    logo_height = 30 * mm
    
    company_lines = company.get("address", "").replace("\n", "<br/>")
    company_contact = f"Phone: {company.get('phone','')}<br/>{company.get('email','')}"
    
    if logo_path:
        try:
            img_path = Path(logo_path)
            if img_path.exists():
                img = Image(str(img_path), width=logo_width, height=logo_height)
                
                right_text = Paragraph(f"{company.get('name', '')}<br/>{company_lines}<br/>{company_contact}", styles["NormalLeft"])
                
                header_table = Table([[img, right_text]], colWidths=[logo_width + 8 * mm, None])
                header_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 8),
                ]))
                elements.append(header_table)
            else:
                elements.append(Paragraph(company.get("name", ""), styles["InvoiceTitle"]))
                elements.append(Paragraph(f"{company_lines}<br/>{company_contact}", styles["NormalLeft"]))
        except Exception:
            elements.append(Paragraph(company.get("name", ""), styles["InvoiceTitle"]))
            elements.append(Paragraph(f"{company_lines}<br/>{company_contact}", styles["NormalLeft"]))
    else:
        elements.append(Paragraph(company.get("name", ""), styles["InvoiceTitle"]))
        elements.append(Paragraph(f"{company_lines}<br/>{company_contact}", styles["NormalLeft"]))

    elements.append(Spacer(1, 12))

    meta_data = [
        [Paragraph("<b>Invoice No:</b>", styles["MetaLabel"]), Paragraph(invoice_no, styles["MetaValue"]),
         Paragraph("<b>Order Date:</b>", styles["MetaLabel"]), Paragraph(str(order.get("order_date") or ""), styles["MetaValue"])],
        [Paragraph("<b>Customer:</b>", styles["MetaLabel"]), Paragraph(str(customer.get("name") or ""), styles["MetaValue"]),
         Paragraph("<b>Collection Date:</b>", styles["MetaLabel"]), Paragraph(str(order.get("collection_date") or ""), styles["MetaValue"])],
        [Paragraph("<b>Phone:</b>", styles["MetaLabel"]), Paragraph(str(customer.get("phone") or ""), styles["MetaValue"]),
         Paragraph("<b>Status:</b>", styles["MetaLabel"]), Paragraph(str(order.get("status") or ""), styles["MetaValue"])],
    ]
    meta_tbl = Table(meta_data, colWidths=[25 * mm, 60 * mm, 28 * mm, 60 * mm])
    meta_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(meta_tbl)
    elements.append(Spacer(1, 8))

    elements.append(Paragraph("<b>Items</b>", styles["NormalLeft"]))
    items_data = _build_order_table_data(items, styles)
    col_widths = [10 * mm, 80 * mm, 28 * mm, 16 * mm, 26 * mm, 26 * mm]
    items_tbl = Table(items_data, colWidths=col_widths, repeatRows=1)
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (3, 1), (5, -1), "RIGHT"),
        ("LEFTPADDING", (1, 1), (1, -1), 4),
    ]))
    elements.append(items_tbl)
    elements.append(Spacer(1, 12))

    totals_data = [
        [Paragraph("Subtotal:", styles["MetaLabel"]), Paragraph(_fmt_money(subtotal), styles["MetaValue"])],
    ]
    
    if express_charge > 0:
        totals_data.append(
            [Paragraph("Express Charge:", styles["MetaLabel"]), Paragraph(_fmt_money(express_charge), styles["MetaValue"])]
        )
    
    totals_data.extend([
        [Paragraph("Discount:", styles["MetaLabel"]), Paragraph(_fmt_money(discount_amount), styles["MetaValue"])],
        [Paragraph("<b>Total:</b>", styles["MetaLabel"]), Paragraph(f"<b>{_fmt_money(total_amount)}</b>", styles["MetaValue"])],
        [Paragraph("Paid:", styles["MetaLabel"]), Paragraph(_fmt_money(paid_amount), styles["MetaValue"])],
        [Paragraph("Balance:", styles["MetaLabel"]), Paragraph(_fmt_money(balance), styles["MetaValue"])],
    ])
    
    tot_tbl = Table(totals_data, colWidths=[110 * mm, 36 * mm], hAlign="RIGHT")
    tot_tbl.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(tot_tbl)
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("<b>Payments</b>", styles["NormalLeft"]))
    if payments:
        pay_rows = [["Date", "Amount", "Notes"]]
        for p in payments:
            pay_rows.append([
                Paragraph(str(p.get("payment_date") or ""), styles["NormalLeft"]),
                Paragraph(_fmt_money(float(p.get("amount") or 0.0)), styles["NormalLeft"]),
                Paragraph(str(p.get("notes") or ""), styles["NormalLeft"])
            ])
        pay_tbl = Table(pay_rows, colWidths=[50 * mm, 30 * mm, 66 * mm])
        pay_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f9f9f9")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        elements.append(pay_tbl)
    else:
        elements.append(Paragraph("No payments recorded.", styles["NormalLeft"]))

    elements.append(Spacer(1, 12))
    
    if order.get("special_instructions"):
        elements.append(Paragraph(f"<b>Special Instructions:</b> {order.get('special_instructions')}", styles["NormalLeft"]))
        elements.append(Spacer(1, 8))

    elements.append(Spacer(1, 12))
    disclaimer_para = DISCLAIMER_TEXT.replace("\n", "<br/>")
    elements.append(Paragraph(disclaimer_para, styles["Disclaimer"]))

    elements.append(Paragraph(company.get("footer_note", ""), styles["Small"]))

    doc.build(elements, onFirstPage=_add_page_number, onLaterPages=_add_page_number)

    if open_file:
        try:
            if os.name == "nt":
                os.startfile(str(out_path))
            else:
                webbrowser.open(str(out_path))
        except Exception:
            pass

    return str(out_path)
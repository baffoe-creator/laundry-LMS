#!/usr/bin/env python3
"""
user_manual.py

Generate a short user manual PDF for the Laundry Management System (LMS).
Run:
    python user_manual.py

Output:
    user_manual.pdf in the current folder
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from datetime import datetime

OUT = "user_manual.pdf"

def build_manual(outpath=OUT):
    doc = SimpleDocTemplate(outpath, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Heading', fontSize=14, leading=18))
    styles.add(ParagraphStyle(name='Sub', fontSize=11, leading=14))
    elems = []

    elems.append(Paragraph("Laundry Management System — Quick User Manual", styles['Heading']))
    elems.append(Spacer(1,6))
    elems.append(Paragraph(f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles['Normal']))
    elems.append(Spacer(1,12))

    elems.append(Paragraph("Overview", styles['Heading']))
    elems.append(Paragraph("This desktop application helps cashiers and managers manage customers, orders, payments, invoices, and reports for a laundry shop. It uses a local SQLite database.", styles['Normal']))
    elems.append(Spacer(1,8))

    elems.append(Paragraph("Quick Start (Cashier)", styles['Heading']))
    qs = [
        "Open the application and log in with your username and password.",
        "Register a customer or search for an existing one (Customers).",
        "Create an Order for the customer, add items with quantity and unit price.",
        "Apply discount (percent or fixed) if needed; totals update automatically.",
        "Record payments (full or partial) in Payments. The balance updates.",
        "Generate an Invoice (Orders -> Print Invoice), open or print the PDF for the customer.",
        "Update order status as items move through: Received → Washed → Ironed → Ready → Collected."
    ]
    elems.append(ListFlowable([ListItem(Paragraph(s, styles['Normal'])) for s in qs], bulletType='bullet'))
    elems.append(Spacer(1,8))

    elems.append(Paragraph("Manager tasks", styles['Heading']))
    mgr = [
        "View daily reports in Reports (daily sales, outstanding balances).",
        "Create and manage users in Users (roles: admin, manager, cashier).",
        "Edit company settings (Settings) to update invoice header and logo.",
        "Run backups or restore the database from Backup & Restore."
    ]
    elems.append(ListFlowable([ListItem(Paragraph(s, styles['Normal'])) for s in mgr], bulletType='bullet'))
    elems.append(Spacer(1,8))

    elems.append(Paragraph("Printing and Exports", styles['Heading']))
    elems.append(Paragraph("Invoices and reports are generated as PDFs (ReportLab). Export daily reports to CSV via Reports -> Export CSV.", styles['Normal']))
    elems.append(Spacer(1,8))

    elems.append(Paragraph("Backups", styles['Heading']))
    elems.append(Paragraph("Use Backup & Restore to create timestamped backups in the backups/ folder. Restoring will replace the current database (a backup is created first).", styles['Normal']))
    elems.append(Spacer(1,8))

    elems.append(Paragraph("Support and Notes", styles['Heading']))
    elems.append(Paragraph("For packaging, run build_exe.bat (Windows) to create a single EXE. The database (lms.db) is not embedded; keep it next to the EXE or allow the app to create it on first run.", styles['Normal']))
    elems.append(Spacer(1,12))

    elems.append(Paragraph("Contact / Credits", styles['Heading']))
    elems.append(Paragraph("NII ET AL Laundry - Laundry Management System (prototype)\nDeveloped as a demo.", styles['Normal']))

    doc.build(elems)
    print(f"Manual saved to {outpath}")

if __name__ == "__main__":
    build_manual()
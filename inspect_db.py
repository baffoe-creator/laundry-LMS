#!/usr/bin/env python3
"""
inspect_db.py

Small helper script to print summary data from lms.db.

Usage:
    python inspect_db.py
"""
import sqlite3
from pprint import pprint
from pathlib import Path

DB = Path("lms.db")
if not DB.exists():
    print(f"Database file {DB} not found. Ensure you are in the project folder.")
    raise SystemExit(1)

def q(sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]

conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

print("Tables in DB:")
for row in q("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"):
    print(" -", row["name"])

print("\nUsers:")
pprint(q("SELECT user_id, username, role, created_at FROM users;"))

print("\nCustomers (last 10):")
pprint(q("SELECT * FROM customers ORDER BY created_at DESC LIMIT 10;"))

print("\nOrders (last 10):")
pprint(q("SELECT order_id, customer_id, status, total_amount, paid_amount, balance, order_date FROM orders ORDER BY order_date DESC LIMIT 10;"))

print("\nOrder Items (last 10):")
pprint(q("SELECT * FROM order_items ORDER BY item_id DESC LIMIT 10;"))

print("\nPayments (last 10):")
pprint(q("SELECT * FROM payments ORDER BY payment_date DESC LIMIT 10;"))

# Example: show a full order snapshot if there is at least one order
orders = q("SELECT order_id FROM orders ORDER BY order_date DESC LIMIT 1;")
if orders:
    oid = orders[0]["order_id"]
    print(f"\nFull snapshot for order_id = {oid}:")
    pprint(q("SELECT * FROM orders WHERE order_id = ?", (oid,)))
    pprint(q("SELECT * FROM order_items WHERE order_id = ? ORDER BY item_id", (oid,)))
    pprint(q("SELECT * FROM payments WHERE order_id = ? ORDER BY payment_date", (oid,)))
else:
    print("\nNo orders found in DB.")

conn.close()
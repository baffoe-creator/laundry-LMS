#!/usr/bin/env python3
"""
models.py

Data access layer (DAL) for the Laundry Management System (LMS).

This module provides small, well-documented functions that perform CRUD and
business logic operations against the SQLite schema created by database.py.

Key responsibilities implemented here:
- create_user / authenticate_user
- create_customer / find_customers
- create_order
- add_order_item (auto-calc subtotal)
- compute_order_totals (applies discount_type/fixed/percent and updates order totals)
- record_payment (inserts payment and updates order paid_amount and balance)
- get_order_with_items (returns order metadata + items + payments)
- list_orders_by_status
- daily_report (summary for a given date)
- format_invoice_number (presentation-only formatting of invoice/order id)

Design notes / decisions:
- Discount semantics: orders.discount (REAL) + orders.discount_type ('percent'|'fixed')
  This matches the DB schema in database.py and avoids ambiguity.
- Order numbering: order_id is the integer PK. We provide format_invoice_number()
  that displays ORD-YYYYMMDD-<order_id padded to 6 digits> for human-friendly invoices.
- All DB calls use parameterized SQL to avoid injection and ensure safety.
- Functions return simple Python types (int, dict, list of dicts) for easy consumption by UI.

Run the small test harness at the bottom to exercise core flows:
    python models.py
"""

from typing import Optional, List, Dict, Any, Tuple
import sqlite3
from decimal import Decimal, ROUND_HALF_UP

# Import helpers from database.py (connect_db, verify_password, hash_password, get_user_by_username)
import database

# Helper: rounding for monetary values (two decimals)
def _round_money(value: float) -> float:
    """Round a float to 2 decimal places using bankers rounding."""
    d = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(d)


# ---------------------
# User functions
# ---------------------
def create_user(username: str, password: str, role: str = "cashier") -> int:
    """
    Create a user and return the new user_id.
    role must be one of 'admin', 'manager', 'cashier' (DB enforces this).
    """
    password_hash = database.hash_password(password)
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, password_hash, role),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Verify provided credentials. Returns user dict on success or None on failure.
    """
    row = database.get_user_by_username(username)
    if not row:
        return None
    if database.verify_password(row["password_hash"], password):
        return dict(row)
    return None


# ---------------------
# Customer functions
# ---------------------
def create_customer(name: str, phone: Optional[str] = None) -> int:
    """
    Create a customer and return customer_id.
    """
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO customers (name, phone) VALUES (?, ?)",
        (name.strip(), phone.strip() if phone else None),
    )
    conn.commit()
    customer_id = cur.lastrowid
    conn.close()
    return customer_id


def find_customers(query: str) -> List[Dict[str, Any]]:
    """
    Search customers by name or phone. Simple LIKE search (case-insensitive).
    Returns list of dict rows.
    """
    q = f"%{query.strip()}%"
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY created_at DESC",
        (q, q),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ---------------------
# Order and Item functions
# ---------------------
def create_order(
    customer_id: int,
    created_by: int,
    collection_date: Optional[str] = None,
    special_instructions: Optional[str] = None,
    discount: float = 0.0,
    discount_type: str = "fixed",
) -> int:
    """
    Create an order record and return order_id.
    Initially total_amount/paid_amount/balance are set; totals will be computed after
    items are added using compute_order_totals().
    discount_type: 'percent' or 'fixed'
    collection_date should be a string YYYY-MM-DD or None.
    """
    if discount_type not in ("fixed", "percent"):
        raise ValueError("discount_type must be 'fixed' or 'percent'")

    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO orders
            (customer_id, created_by, collection_date, special_instructions, discount, discount_type, total_amount, paid_amount, balance)
        VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0)
        """,
        (customer_id, created_by, collection_date, special_instructions, float(discount), discount_type),
    )
    conn.commit()
    order_id = cur.lastrowid
    conn.close()
    return order_id


def add_order_item(
    order_id: int,
    item_type: str,
    color_category: Optional[str],
    quantity: int,
    unit_price: float,
) -> int:
    """
    Add an item to an order. This computes subtotal = quantity * unit_price and inserts row.
    After inserting, it calls compute_order_totals(order_id) to refresh totals.

    Returns: item_id
    """
    if quantity <= 0:
        raise ValueError("quantity must be >= 1")
    if unit_price < 0:
        raise ValueError("unit_price must be >= 0")

    subtotal = _round_money(quantity * unit_price)

    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO order_items (order_id, item_type, color_category, quantity, unit_price, subtotal)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (order_id, item_type.strip(), color_category.strip() if color_category else None, int(quantity), float(unit_price), subtotal),
    )
    conn.commit()
    item_id = cur.lastrowid
    conn.close()

    # Recompute totals after adding the item
    compute_order_totals(order_id)
    return item_id


def compute_order_totals(order_id: int) -> Dict[str, float]:
    """
    Recalculate totals for the order:
      - sum subtotals from order_items
      - apply discount (fixed or percent)
      - set total_amount, and recompute balance = total_amount - paid_amount

    Returns a dict with computed fields:
      { 'subtotal', 'discount_amount', 'total_amount', 'paid_amount', 'balance' }
    """
    conn = database.connect_db()
    cur = conn.cursor()

    # Sum item subtotals
    cur.execute("SELECT COALESCE(SUM(subtotal), 0) AS subtotal FROM order_items WHERE order_id = ?", (order_id,))
    subtotal_row = cur.fetchone()
    subtotal = float(subtotal_row["subtotal"]) if subtotal_row else 0.0
    subtotal = _round_money(subtotal)

    # Get discount and paid_amount from orders
    cur.execute("SELECT discount, discount_type, paid_amount FROM orders WHERE order_id = ?", (order_id,))
    order_row = cur.fetchone()
    if not order_row:
        conn.close()
        raise ValueError(f"Order {order_id} not found")

    discount = float(order_row["discount"] or 0.0)
    discount_type = order_row["discount_type"] or "fixed"
    paid_amount = float(order_row["paid_amount"] or 0.0)

    # Calculate discount amount
    if discount_type == "percent":
        discount_amount = subtotal * (discount / 100.0)
    else:
        discount_amount = discount

    discount_amount = _round_money(discount_amount)
    total_amount = _round_money(max(0.0, subtotal - discount_amount))
    balance = _round_money(max(0.0, total_amount - paid_amount))

    # Store updated totals in orders table
    cur.execute(
        "UPDATE orders SET total_amount = ?, balance = ? WHERE order_id = ?",
        (total_amount, balance, order_id),
    )
    conn.commit()
    conn.close()

    return {
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "total_amount": total_amount,
        "paid_amount": paid_amount,
        "balance": balance,
    }


# ---------------------
# Payment functions
# ---------------------
def record_payment(order_id: int, amount: float, notes: Optional[str] = None) -> int:
    """
    Record a payment for an order. Updates order.paid_amount and order.balance accordingly.
    Returns payment_id.
    """
    if amount <= 0:
        raise ValueError("Payment amount must be positive")

    conn = database.connect_db()
    cur = conn.cursor()

    # Insert payment row
    cur.execute(
        "INSERT INTO payments (order_id, amount, notes) VALUES (?, ?, ?)",
        (order_id, float(amount), notes),
    )
    payment_id = cur.lastrowid

    # Update paid_amount and balance on orders (recompute atomically)
    # Fetch current paid_amount and total_amount
    cur.execute("SELECT COALESCE(paid_amount, 0) AS paid_amount, COALESCE(total_amount, 0) AS total_amount FROM orders WHERE order_id = ?", (order_id,))
    row = cur.fetchone()
    if not row:
        conn.rollback()
        conn.close()
        raise ValueError(f"Order {order_id} not found")

    new_paid = float(row["paid_amount"]) + float(amount)
    total_amount = float(row["total_amount"])
    new_balance = _round_money(max(0.0, total_amount - new_paid))

    # Update orders
    cur.execute(
        "UPDATE orders SET paid_amount = ?, balance = ? WHERE order_id = ?",
        (new_paid, new_balance, order_id),
    )
    conn.commit()
    conn.close()
    return payment_id


# ---------------------
# Retrieval / Reporting
# ---------------------
def get_order_with_items(order_id: int) -> Dict[str, Any]:
    """
    Return a dict with:
      - order: dict of order row
      - customer: dict of customer row
      - items: list[dict] of order_items
      - payments: list[dict] of payments
    """
    conn = database.connect_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    order_row = cur.fetchone()
    if not order_row:
        conn.close()
        raise ValueError(f"Order {order_id} not found")
    order = dict(order_row)

    # Customer
    cur.execute("SELECT * FROM customers WHERE customer_id = ?", (order["customer_id"],))
    customer_row = cur.fetchone()
    customer = dict(customer_row) if customer_row else None

    # Items
    cur.execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY item_id", (order_id,))
    items = [dict(r) for r in cur.fetchall()]

    # Payments
    cur.execute("SELECT * FROM payments WHERE order_id = ? ORDER BY payment_date", (order_id,))
    payments = [dict(r) for r in cur.fetchall()]

    conn.close()
    return {
        "order": order,
        "customer": customer,
        "items": items,
        "payments": payments,
    }


def list_orders_by_status(status: str) -> List[Dict[str, Any]]:
    """
    Return orders that match a given status (exact match).
    """
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE status = ? ORDER BY order_date DESC", (status,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def daily_report(date_str: str) -> Dict[str, Any]:
    """
    Produce a simple daily report for orders whose order_date is on date_str (YYYY-MM-DD).
    Returns dict containing:
      - date: date_str
      - total_orders: int
      - total_sales: float (sum total_amount)
      - total_paid: float (sum paid_amount)
      - outstanding: float (sum balance)
    """
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          COUNT(*) AS total_orders,
          COALESCE(SUM(total_amount), 0) AS total_sales,
          COALESCE(SUM(paid_amount), 0) AS total_paid,
          COALESCE(SUM(balance), 0) AS outstanding
        FROM orders
        WHERE DATE(order_date) = ?
        """,
        (date_str,),
    )
    row = cur.fetchone()
    conn.close()
    return {
        "date": date_str,
        "total_orders": int(row["total_orders"]),
        "total_sales": _round_money(float(row["total_sales"])),
        "total_paid": _round_money(float(row["total_paid"])),
        "outstanding": _round_money(float(row["outstanding"])),
    }


# ---------------------
# Presentation helpers
# ---------------------
def format_invoice_number(order_id: int, order_date: Optional[str] = None) -> str:
    """
    Format a human-friendly invoice number for display:
      ORD-YYYYMMDD-<order_id padded to 6 digits>

    If order_date not provided, we attempt to fetch it from DB.
    """
    if order_date is None:
        conn = database.connect_db()
        cur = conn.cursor()
        cur.execute("SELECT order_date FROM orders WHERE order_id = ?", (order_id,))
        r = cur.fetchone()
        conn.close()
        if r and r["order_date"]:
            order_date = r["order_date"]
        else:
            from datetime import datetime
            order_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Extract YYYYMMDD
    date_part = order_date.split(" ")[0].replace("-", "")
    return f"ORD-{date_part}-{int(order_id):06d}"


# ---------------------
# Quick test harness
# ---------------------
if __name__ == "__main__":
    import os
    from pprint import pprint

    print("Running models.py quick test harness...")

    # Ensure DB exists in the current project (database.init_db called previously by you).
    db_path = database.get_db_path()
    print("Using DB:", db_path)
    if not os.path.exists(db_path):
        print("ERROR: DB not found. Run database.py first to initialize.")
        raise SystemExit(1)

    # Steps:
    # 1. Create a test customer
    cust_name = "Test Customer"
    cust_phone = "0700123456"
    customer_id = create_customer(cust_name, cust_phone)
    print("Created customer_id:", customer_id)

    # 2. Use admin user (assumes seeded admin with user_id=1). If not present, create a user.
    admin = database.get_user_by_username("admin")
    if admin:
        created_by = admin["user_id"]
    else:
        created_by = create_user("admin", "admin123", "admin")
    print("Using created_by user_id:", created_by)

    # 3. Create an order with a 10% discount (percent)
    order_id = create_order(customer_id, created_by, collection_date=None, special_instructions="No starch", discount=10.0, discount_type="percent")
    print("Created order_id:", order_id)

    # 4. Add items
    item1_id = add_order_item(order_id, item_type="Shirt", color_category="Colored", quantity=3, unit_price=2.50)
    item2_id = add_order_item(order_id, item_type="Trousers", color_category="White", quantity=2, unit_price=3.75)
    print("Added items:", item1_id, item2_id)

    # 5. Compute totals (already computed by add_order_item, but call explicitly)
    totals = compute_order_totals(order_id)
    print("Computed totals:")
    pprint(totals)

    # 6. Record a partial payment of 5.00
    payment_id = record_payment(order_id, 5.00, notes="Partial payment at checkout")
    print("Recorded payment_id:", payment_id)

    # 7. Re-fetch order with items and payments
    full = get_order_with_items(order_id)
    print("\nOrder snapshot:")
    pprint(full["order"])
    print("\nCustomer:")
    pprint(full["customer"])
    print("\nItems:")
    pprint(full["items"])
    print("\nPayments:")
    pprint(full["payments"])

    # 8. Print formatted invoice number
    invoice_no = format_invoice_number(order_id, full["order"]["order_date"])
    print("\nInvoice number:", invoice_no)

    # 9. Daily report for today's date (extract YYYY-MM-DD)
    date_only = full["order"]["order_date"].split(" ")[0]
    report = daily_report(date_only)
    print("\nDaily report for", date_only)
    pprint(report)

    print("\nQuick test harness finished. If everything worked, the DAL functions are operational.")
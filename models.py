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
- format_invoice_number
- get_all_prices / update_item_price
- Customer ledger functions (Feature 1c)
- Date-range report functions (Feature 2a)

Design notes / decisions:
- Discount semantics: orders.discount (REAL) + orders.discount_type ('percent'|'fixed')
- Order numbering: order_id is the integer PK. format_invoice_number() for display.
- All DB calls use parameterized SQL.
- Ledger entries are automatically created when orders are finalised and payments recorded.
"""

from typing import Optional, List, Dict, Any, Tuple
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

import database


def _round_money(value: float) -> float:
    """Round a float to 2 decimal places using bankers rounding."""
    d = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(d)


# ---------------------
# User functions
# ---------------------
def create_user(username: str, password: str, role: str = "cashier") -> int:
    """Create a user and return the new user_id."""
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
    """Verify provided credentials. Returns user dict on success or None."""
    row = database.get_user_by_username(username)
    if not row:
        return None
    if database.verify_password(row["password_hash"], password):
        return dict(row)
    return None


# ---------------------
# Customer functions
# ---------------------
def create_customer(name: str, phone: Optional[str] = None, customer_type: str = "individual") -> int:
    """Create a customer and return customer_id."""
    valid_types = ["individual", "corporate", "loyal", "first_time", "student"]
    if customer_type not in valid_types:
        customer_type = "individual"
    
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO customers (name, phone, customer_type) VALUES (?, ?, ?)",
        (name.strip(), phone.strip() if phone else None, customer_type),
    )
    conn.commit()
    customer_id = cur.lastrowid
    conn.close()
    return customer_id


def find_customers(query: str) -> List[Dict[str, Any]]:
    """Search customers by name or phone."""
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


def get_customer_by_id(customer_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single customer by ID."""
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


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
    """Create an order record and return order_id."""
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
    """Add an item to an order and recompute totals."""
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

    compute_order_totals(order_id)
    return item_id


def remove_order_item(order_id: int, item_id: int) -> bool:
    """Remove an item from an order."""
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM order_items WHERE item_id = ? AND order_id = ?", (item_id, order_id))
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    
    if success:
        compute_order_totals(order_id)
    return success


def compute_order_totals(order_id: int) -> Dict[str, float]:
    """
    Recalculate totals for the order and update orders table.
    Also updates customer ledger with charge entry when total changes.
    (Feature 1d - ledger hook)
    """
    conn = database.connect_db()
    cur = conn.cursor()

    # Sum item subtotals
    cur.execute("SELECT COALESCE(SUM(subtotal), 0) AS subtotal FROM order_items WHERE order_id = ?", (order_id,))
    subtotal_row = cur.fetchone()
    subtotal = float(subtotal_row["subtotal"]) if subtotal_row else 0.0
    subtotal = _round_money(subtotal)

    # Get discount and paid_amount from orders
    cur.execute("SELECT customer_id, discount, discount_type, paid_amount FROM orders WHERE order_id = ?", (order_id,))
    order_row = cur.fetchone()
    if not order_row:
        conn.close()
        raise ValueError(f"Order {order_id} not found")

    customer_id = order_row["customer_id"]
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

    # Get previous total to detect changes
    cur.execute("SELECT total_amount FROM orders WHERE order_id = ?", (order_id,))
    prev_total = float(cur.fetchone()["total_amount"] or 0.0)

    # Store updated totals in orders table
    cur.execute(
        "UPDATE orders SET total_amount = ?, balance = ? WHERE order_id = ?",
        (total_amount, balance, order_id),
    )
    
    # If total_amount changed, update ledger (delete old charge, insert new)
    if abs(total_amount - prev_total) > 0.001:
        # Delete any existing charge for this order
        cur.execute(
            "DELETE FROM customer_ledger WHERE order_id = ? AND entry_type = 'charge'",
            (order_id,)
        )
        
        # Get current running balance before this order
        cur.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM customer_ledger WHERE customer_id = ?",
            (customer_id,)
        )
        running_before = float(cur.fetchone()[0])
        
        # Insert new charge entry
        cur.execute(
            """
            INSERT INTO customer_ledger 
            (customer_id, order_id, entry_type, amount, running_balance, entry_date)
            VALUES (?, ?, 'charge', ?, ?, CURRENT_TIMESTAMP)
            """,
            (customer_id, order_id, total_amount, running_before + total_amount)
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
# Payment functions (updated with ledger hook)
# ---------------------
def record_payment(order_id: int, amount: float, notes: Optional[str] = None) -> int:
    """
    Record a payment for an order. Updates order.paid_amount and order.balance.
    Also adds payment entry to customer ledger.
    (Feature 1d - ledger hook)
    """
    if amount <= 0:
        raise ValueError("Payment amount must be positive")

    conn = database.connect_db()
    cur = conn.cursor()

    # Get customer_id and current totals
    cur.execute(
        "SELECT customer_id, paid_amount, total_amount FROM orders WHERE order_id = ?",
        (order_id,)
    )
    order_row = cur.fetchone()
    if not order_row:
        conn.close()
        raise ValueError(f"Order {order_id} not found")

    customer_id = order_row["customer_id"]
    current_paid = float(order_row["paid_amount"])
    total_amount = float(order_row["total_amount"])

    # Insert payment row
    cur.execute(
        "INSERT INTO payments (order_id, amount, notes) VALUES (?, ?, ?)",
        (order_id, float(amount), notes),
    )
    payment_id = cur.lastrowid

    # Update paid_amount and balance
    new_paid = current_paid + float(amount)
    new_balance = _round_money(max(0.0, total_amount - new_paid))

    cur.execute(
        "UPDATE orders SET paid_amount = ?, balance = ? WHERE order_id = ?",
        (new_paid, new_balance, order_id),
    )

    # Get current running balance before this payment
    cur.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM customer_ledger WHERE customer_id = ?",
        (customer_id,)
    )
    running_before = float(cur.fetchone()[0])

    # Add payment entry to ledger (negative amount)
    cur.execute(
        """
        INSERT INTO customer_ledger 
        (customer_id, order_id, entry_type, amount, running_balance, notes, entry_date)
        VALUES (?, ?, 'payment', ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (customer_id, order_id, -float(amount), running_before - float(amount), 
         f"Payment ID: {payment_id}" + (f" - {notes}" if notes else ""))
    )

    conn.commit()
    conn.close()
    return payment_id


# ---------------------
# Customer Ledger functions (Feature 1c)
# ---------------------
def get_customer_ledger(customer_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Return the most recent `limit` ledger entries for a customer,
    ordered by entry_date DESC.
    """
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ledger_id, customer_id, order_id, entry_type, amount,
               running_balance, notes, entry_date
        FROM customer_ledger
        WHERE customer_id = ?
        ORDER BY entry_date DESC
        LIMIT ?
        """,
        (customer_id, limit)
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_customer_outstanding_balance(customer_id: int) -> float:
    """
    Return the current total outstanding balance for a customer.
    Computed as SUM(amount) from customer_ledger.
    """
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT COALESCE(SUM(amount), 0) as balance FROM customer_ledger WHERE customer_id = ?",
        (customer_id,)
    )
    balance = float(cur.fetchone()["balance"])
    conn.close()
    return _round_money(balance)


def post_ledger_charge(customer_id: int, order_id: int, amount: float, notes: str = None) -> int:
    """
    Insert a 'charge' ledger entry. Recalculates running_balance.
    """
    conn = database.connect_db()
    cur = conn.cursor()
    
    # Get current running balance
    cur.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM customer_ledger WHERE customer_id = ?",
        (customer_id,)
    )
    running_before = float(cur.fetchone()[0])
    
    cur.execute(
        """
        INSERT INTO customer_ledger 
        (customer_id, order_id, entry_type, amount, running_balance, notes, entry_date)
        VALUES (?, ?, 'charge', ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (customer_id, order_id, amount, running_before + amount, notes)
    )
    ledger_id = cur.lastrowid
    conn.commit()
    conn.close()
    return ledger_id


def post_ledger_payment(customer_id: int, order_id: int, amount: float, notes: str = None) -> int:
    """
    Insert a 'payment' ledger entry (amount stored as negative value).
    """
    conn = database.connect_db()
    cur = conn.cursor()
    
    # Get current running balance
    cur.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM customer_ledger WHERE customer_id = ?",
        (customer_id,)
    )
    running_before = float(cur.fetchone()[0])
    
    cur.execute(
        """
        INSERT INTO customer_ledger 
        (customer_id, order_id, entry_type, amount, running_balance, notes, entry_date)
        VALUES (?, ?, 'payment', ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (customer_id, order_id, -amount, running_before - amount, notes)
    )
    ledger_id = cur.lastrowid
    conn.commit()
    conn.close()
    return ledger_id


def post_ledger_adjustment(customer_id: int, amount: float, notes: str, order_id: int = None) -> int:
    """
    Insert a manual 'adjustment' entry. amount may be positive or negative.
    Only callable by admin/manager roles (enforcement in UI layer).
    """
    if not notes or not notes.strip():
        raise ValueError("Notes are required for adjustment entries")
    
    conn = database.connect_db()
    cur = conn.cursor()
    
    # Get current running balance
    cur.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM customer_ledger WHERE customer_id = ?",
        (customer_id,)
    )
    running_before = float(cur.fetchone()[0])
    
    cur.execute(
        """
        INSERT INTO customer_ledger 
        (customer_id, order_id, entry_type, amount, running_balance, notes, entry_date)
        VALUES (?, ?, 'adjustment', ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (customer_id, order_id, amount, running_before + amount, notes.strip())
    )
    ledger_id = cur.lastrowid
    conn.commit()
    conn.close()
    return ledger_id


# ---------------------
# Retrieval / Reporting
# ---------------------
def get_order_with_items(order_id: int) -> Dict[str, Any]:
    """Return order with customer, items, and payments."""
    conn = database.connect_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    order_row = cur.fetchone()
    if not order_row:
        conn.close()
        raise ValueError(f"Order {order_id} not found")
    order = dict(order_row)

    cur.execute("SELECT * FROM customers WHERE customer_id = ?", (order["customer_id"],))
    customer_row = cur.fetchone()
    customer = dict(customer_row) if customer_row else None

    cur.execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY item_id", (order_id,))
    items = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM payments WHERE order_id = ? ORDER BY payment_date", (order_id,))
    payments = [dict(r) for r in cur.fetchall()]

    conn.close()
    return {
        "order": order,
        "customer": customer,
        "items": items,
        "payments": payments,
    }


def get_orders_by_customer(customer_id: int) -> List[Dict[str, Any]]:
    """Return all orders for a specific customer."""
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT order_id, order_date, status, total_amount, paid_amount, balance
        FROM orders
        WHERE customer_id = ?
        ORDER BY order_date DESC
        """,
        (customer_id,)
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def list_orders_by_status(status: str) -> List[Dict[str, Any]]:
    """Return orders that match a given status."""
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE status = ? ORDER BY order_date DESC", (status,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def daily_report(date_str: str) -> Dict[str, Any]:
    """Produce a simple daily report for orders on date_str."""
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
# Date-Range Report functions (Feature 2a)
# ---------------------
def range_report(date_from: str, date_to: str) -> Dict[str, Any]:
    """
    Return aggregated report data for orders whose order_date falls
    within [date_from, date_to] inclusive.
    """
    conn = database.connect_db()
    cur = conn.cursor()
    
    # Overall summary
    cur.execute(
        """
        SELECT
          COUNT(*) AS total_orders,
          COALESCE(SUM(total_amount), 0) AS total_sales,
          COALESCE(SUM(paid_amount), 0) AS total_paid,
          COALESCE(SUM(balance), 0) AS outstanding
        FROM orders
        WHERE DATE(order_date) BETWEEN ? AND ?
        """,
        (date_from, date_to),
    )
    summary = cur.fetchone()
    
    # Orders by status breakdown
    cur.execute(
        """
        SELECT status, COUNT(*) as count
        FROM orders
        WHERE DATE(order_date) BETWEEN ? AND ?
        GROUP BY status
        ORDER BY status
        """,
        (date_from, date_to),
    )
    status_rows = cur.fetchall()
    orders_by_status = {r["status"]: r["count"] for r in status_rows}
    
    # Daily breakdown
    cur.execute(
        """
        SELECT 
          DATE(order_date) as date,
          COUNT(*) as order_count,
          COALESCE(SUM(total_amount), 0) as sales,
          COALESCE(SUM(paid_amount), 0) as paid,
          COALESCE(SUM(balance), 0) as outstanding
        FROM orders
        WHERE DATE(order_date) BETWEEN ? AND ?
        GROUP BY DATE(order_date)
        ORDER BY date
        """,
        (date_from, date_to),
    )
    daily_rows = cur.fetchall()
    daily_breakdown = [
        {
            "date": r["date"],
            "order_count": r["order_count"],
            "sales": _round_money(float(r["sales"])),
            "paid": _round_money(float(r["paid"])),
            "outstanding": _round_money(float(r["outstanding"]))
        }
        for r in daily_rows
    ]
    
    conn.close()
    
    return {
        "date_from": date_from,
        "date_to": date_to,
        "total_orders": int(summary["total_orders"]),
        "total_sales": _round_money(float(summary["total_sales"])),
        "total_paid": _round_money(float(summary["total_paid"])),
        "outstanding": _round_money(float(summary["outstanding"])),
        "orders_by_status": orders_by_status,
        "daily_breakdown": daily_breakdown,
    }


def list_orders_in_range(date_from: str, date_to: str) -> List[Dict[str, Any]]:
    """
    Return all orders (with customer name joined) where
    DATE(order_date) BETWEEN date_from AND date_to, ordered by order_date ASC.
    """
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT o.order_id, o.order_date, o.status, o.total_amount, o.paid_amount, o.balance,
               c.name as customer_name, c.phone as customer_phone
        FROM orders o
        LEFT JOIN customers c ON o.customer_id = c.customer_id
        WHERE DATE(o.order_date) BETWEEN ? AND ?
        ORDER BY o.order_date ASC
        """,
        (date_from, date_to),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ---------------------
# Price Catalogue functions
# ---------------------
def get_all_prices() -> List[Dict[str, Any]]:
    """Retrieve all items from price_catalogue table."""
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT item_id, item_name, price_coloured, price_white, price_pressing
        FROM price_catalogue
        ORDER BY item_name
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_price_item(item_name: str) -> Optional[Dict[str, Any]]:
    """Get a single price item by name."""
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT item_id, item_name, price_coloured, price_white, price_pressing
        FROM price_catalogue
        WHERE item_name = ?
        """,
        (item_name,)
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_item_price(item_name: str, price_coloured: Optional[float], price_white: Optional[float], price_pressing: Optional[float]) -> bool:
    """Update prices for an item in the catalogue."""
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE price_catalogue
        SET price_coloured = ?, price_white = ?, price_pressing = ?, updated_at = CURRENT_TIMESTAMP
        WHERE item_name = ?
        """,
        (price_coloured, price_white, price_pressing, item_name)
    )
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    return success


# ---------------------
# Presentation helpers
# ---------------------
def format_invoice_number(order_id: int, order_date: Optional[str] = None) -> str:
    """Format a human-friendly invoice number for display."""
    if order_date is None:
        conn = database.connect_db()
        cur = conn.cursor()
        cur.execute("SELECT order_date FROM orders WHERE order_id = ?", (order_id,))
        r = cur.fetchone()
        conn.close()
        if r and r["order_date"]:
            order_date = r["order_date"]
        else:
            order_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    date_part = order_date.split(" ")[0].replace("-", "")
    return f"ORD-{date_part}-{int(order_id):06d}"


# ---------------------
# Quick test harness
# ---------------------
if __name__ == "__main__":
    import os
    from pprint import pprint

    print("Running models.py quick test harness...")

    db_path = database.get_db_path()
    print("Using DB:", db_path)
    if not os.path.exists(db_path):
        print("ERROR: DB not found. Run database.py first to initialize.")
        raise SystemExit(1)

    cust_name = "Test Customer"
    cust_phone = "0700123456"
    customer_id = create_customer(cust_name, cust_phone, customer_type="individual")
    print("Created customer_id:", customer_id)

    admin = database.get_user_by_username("admin")
    if admin:
        created_by = admin["user_id"]
    else:
        created_by = create_user("admin", "admin123", "admin")
    print("Using created_by user_id:", created_by)

    order_id = create_order(customer_id, created_by, collection_date=None, special_instructions="No starch", discount=10.0, discount_type="percent")
    print("Created order_id:", order_id)

    item1_id = add_order_item(order_id, item_type="Shirt", color_category="Colored", quantity=3, unit_price=2.50)
    item2_id = add_order_item(order_id, item_type="Trousers", color_category="White", quantity=2, unit_price=3.75)
    print("Added items:", item1_id, item2_id)

    totals = compute_order_totals(order_id)
    print("Computed totals:")
    pprint(totals)

    payment_id = record_payment(order_id, 5.00, notes="Partial payment at checkout")
    print("Recorded payment_id:", payment_id)

    full = get_order_with_items(order_id)
    print("\nOrder snapshot:")
    pprint(full["order"])

    invoice_no = format_invoice_number(order_id, full["order"]["order_date"])
    print("\nInvoice number:", invoice_no)

    date_only = full["order"]["order_date"].split(" ")[0]
    report = daily_report(date_only)
    print("\nDaily report for", date_only)
    pprint(report)

    print("\nTesting ledger functions:")
    balance = get_customer_outstanding_balance(customer_id)
    print(f"Customer {customer_id} outstanding balance: {balance}")
    ledger = get_customer_ledger(customer_id, limit=10)
    print(f"Ledger entries: {len(ledger)}")
    
    print("\nQuick test harness finished.")
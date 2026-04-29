#!/usr/bin/env python3
"""
models.py

Data access layer (DAL) for the Laundry Management System (LMS).
"""

from typing import Optional, List, Dict, Any, Tuple
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

import database


def _round_money(value: float) -> float:
    d = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(d)


def create_user(username: str, password: str, role: str = "cashier") -> int:
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
    row = database.get_user_by_username(username)
    if not row:
        return None
    if database.verify_password(row["password_hash"], password):
        return dict(row)
    return None


def create_customer(name: str, phone: Optional[str] = None, customer_type: str = "individual") -> int:
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
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def create_order(
    customer_id: int,
    created_by: int,
    collection_date: Optional[str] = None,
    special_instructions: Optional[str] = None,
    discount: float = 0.0,
    discount_type: str = "fixed",
) -> int:
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
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM order_items WHERE item_id = ? AND order_id = ?", (item_id, order_id))
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    if success:
        compute_order_totals(order_id)
    return success


def _calculate_express_charge_for_quantity(total_qty: int, items: list) -> float:
    if total_qty == 0:
        return 0.0
    elif total_qty <= 3:
        return sum(float(item['subtotal']) for item in items)
    elif total_qty <= 5:
        return 15.0
    elif total_qty <= 10:
        return 25.0
    else:
        return 30.0


def compute_order_totals(order_id: int) -> Dict[str, float]:
    conn = database.connect_db()
    cur = conn.cursor()

    cur.execute("SELECT COALESCE(SUM(subtotal), 0) AS subtotal FROM order_items WHERE order_id = ?", (order_id,))
    subtotal_row = cur.fetchone()
    subtotal = float(subtotal_row["subtotal"]) if subtotal_row else 0.0
    subtotal = _round_money(subtotal)

    cur.execute("SELECT customer_id, discount, discount_type, paid_amount, express_charge FROM orders WHERE order_id = ?", (order_id,))
    order_row = cur.fetchone()
    if not order_row:
        conn.close()
        raise ValueError(f"Order {order_id} not found")

    customer_id = order_row["customer_id"]
    discount = float(order_row["discount"] or 0.0)
    discount_type = order_row["discount_type"] or "fixed"
    paid_amount = float(order_row["paid_amount"] or 0.0)
    express_charge_enabled = order_row["express_charge"] or False

    if discount_type == "percent":
        discount_amount = subtotal * (discount / 100.0)
    else:
        discount_amount = discount
    discount_amount = _round_money(discount_amount)

    express_charge_amount = 0.0
    if express_charge_enabled:
        cur.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS total_qty FROM order_items WHERE order_id = ?",
            (order_id,)
        )
        qty_row = cur.fetchone()
        total_qty = int(qty_row["total_qty"]) if qty_row else 0

        cur.execute("SELECT quantity, unit_price, subtotal FROM order_items WHERE order_id = ?", (order_id,))
        items = [dict(r) for r in cur.fetchall()]

        express_charge_amount = _calculate_express_charge_for_quantity(total_qty, items)

    express_charge_amount = _round_money(express_charge_amount)
    total_amount = _round_money(max(0.0, subtotal + express_charge_amount - discount_amount))
    balance = _round_money(max(0.0, total_amount - paid_amount))

    cur.execute("SELECT total_amount FROM orders WHERE order_id = ?", (order_id,))
    prev_total = float(cur.fetchone()["total_amount"] or 0.0)

    cur.execute(
        "UPDATE orders SET total_amount = ?, balance = ? WHERE order_id = ?",
        (total_amount, balance, order_id),
    )

    if abs(total_amount - prev_total) > 0.001:
        cur.execute(
            "DELETE FROM customer_ledger WHERE order_id = ? AND entry_type = 'charge'",
            (order_id,)
        )
        cur.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM customer_ledger WHERE customer_id = ?",
            (customer_id,)
        )
        running_before = float(cur.fetchone()[0])
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
        "express_charge": express_charge_amount,
        "discount_amount": discount_amount,
        "total_amount": total_amount,
        "paid_amount": paid_amount,
        "balance": balance,
    }


def record_payment(order_id: int, amount: float, notes: Optional[str] = None) -> int:
    if amount <= 0:
        raise ValueError("Payment amount must be positive")

    conn = database.connect_db()
    cur = conn.cursor()

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

    cur.execute(
        "INSERT INTO payments (order_id, amount, notes) VALUES (?, ?, ?)",
        (order_id, float(amount), notes),
    )
    payment_id = cur.lastrowid

    new_paid = current_paid + float(amount)
    new_balance = _round_money(max(0.0, total_amount - new_paid))

    cur.execute(
        "UPDATE orders SET paid_amount = ?, balance = ? WHERE order_id = ?",
        (new_paid, new_balance, order_id),
    )

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
        (customer_id, order_id, -float(amount), running_before - float(amount),
         f"Payment ID: {payment_id}" + (f" - {notes}" if notes else ""))
    )

    conn.commit()
    conn.close()
    return payment_id


def get_customer_ledger(customer_id: int, limit: int = 50) -> List[Dict[str, Any]]:
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
    conn = database.connect_db()
    cur = conn.cursor()
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
    conn = database.connect_db()
    cur = conn.cursor()
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
    if not notes or not notes.strip():
        raise ValueError("Notes are required for adjustment entries")
    conn = database.connect_db()
    cur = conn.cursor()
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


def get_order_with_items(order_id: int) -> Dict[str, Any]:
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
    conn = database.connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE status = ? ORDER BY order_date DESC", (status,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def daily_report(date_str: str) -> Dict[str, Any]:
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


def range_report(date_from: str, date_to: str) -> Dict[str, Any]:
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
        WHERE DATE(order_date) BETWEEN ? AND ?
        """,
        (date_from, date_to),
    )
    summary = cur.fetchone()
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


def get_all_prices() -> List[Dict[str, Any]]:
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


def format_invoice_number(order_id: int, order_date: Optional[str] = None) -> str:
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
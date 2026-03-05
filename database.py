#!/usr/bin/env python3
"""
database.py

Initializes the SQLite database for the Laundry Management System (LMS).

Responsibilities:
- Create lms.db (by default) if absent
- Create tables per project schema:
    users, customers, orders, order_items, payments, price_catalogue, customer_ledger
- Add customer_type column to customers table
- Seed a default admin user (username: admin, password: admin123)
- Seed price catalogue from pricing.py
- Provide helper functions to connect to the DB and hash/verify passwords

Notes / decisions:
- To distinguish discount types (percent vs fixed) I've added orders.discount_type TEXT.
- Password hashing uses PBKDF2-HMAC-SHA256.
- The DB file path can be overridden using the LMS_DB_PATH environment variable.
- Added customer_ledger table for debt carry-forward (Feature 1a)
- Added migrate_ledger_from_existing_data() for backward compatibility (Feature 1b)

Run:
    python database.py
This will create (or re-create) the DB file and seed the admin user.
"""

import os
import sqlite3
import hashlib
import binascii
import secrets
from typing import Optional, Tuple
import pricing  # For price catalogue seeding

# Default DB filename (can be overridden with LMS_DB_PATH env var)
DEFAULT_DB = os.environ.get("LMS_DB_PATH", "lms.db")

# PBKDF2 configuration
PBKDF2_ITERATIONS = 100_000


def get_db_path() -> str:
    """Return DB path being used."""
    return DEFAULT_DB


def connect_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Create a SQLite connection with sensible defaults.
    Enables foreign keys and returns rows as sqlite3.Row.
    """
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    """
    Hash the password using PBKDF2-HMAC-SHA256.
    Stored format: iterations$salt_hex$hash_hex
    """
    if not isinstance(password, bytes):
        password_bytes = password.encode("utf-8")
    else:
        password_bytes = password
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password_bytes, salt, iterations)
    salt_hex = binascii.hexlify(salt).decode("ascii")
    dk_hex = binascii.hexlify(dk).decode("ascii")
    return f"{iterations}${salt_hex}${dk_hex}"


def verify_password(stored: str, provided_password: str) -> bool:
    """
    Verify a provided_password against the stored hash.
    Expects stored format iterations$salt_hex$hash_hex
    """
    try:
        iterations_str, salt_hex, hash_hex = stored.split("$")
        iterations = int(iterations_str)
        salt = binascii.unhexlify(salt_hex)
        expected = binascii.unhexlify(hash_hex)
    except Exception:
        return False

    dk = hashlib.pbkdf2_hmac("sha256", provided_password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(dk, expected)


def add_customer_type_column(conn: sqlite3.Connection) -> None:
    """
    Safely add customer_type column to customers table if it doesn't exist.
    """
    try:
        cur = conn.cursor()
        cur.execute("ALTER TABLE customers ADD COLUMN customer_type TEXT DEFAULT 'individual'")
        conn.commit()
        print("Added customer_type column to customers table")
    except sqlite3.OperationalError:
        pass


def init_db(db_path: Optional[str] = None, force: bool = False) -> None:
    """
    Initialize the database with tables. If force=True and the DB exists,
    it will be overwritten (use with care).
    """
    db_path = db_path or get_db_path()

    if force and os.path.exists(db_path):
        os.remove(db_path)

    conn = connect_db(db_path)
    cur = conn.cursor()

    cur.executescript(
        """
        BEGIN;

        CREATE TABLE IF NOT EXISTS users (
            user_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role         TEXT NOT NULL CHECK(role IN ('admin', 'manager', 'cashier')),
            created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS customers (
            customer_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            phone        TEXT,
            created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS orders (
            order_id              INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id           INTEGER NOT NULL,
            created_by            INTEGER NOT NULL,
            order_date            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            collection_date       TEXT,
            status                TEXT NOT NULL DEFAULT 'Received',
            discount              REAL DEFAULT 0,
            discount_type         TEXT DEFAULT 'fixed',
            total_amount          REAL DEFAULT 0,
            paid_amount           REAL DEFAULT 0,
            balance               REAL DEFAULT 0,
            special_instructions  TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS order_items (
            item_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id      INTEGER NOT NULL,
            item_type     TEXT NOT NULL,
            color_category TEXT,
            quantity      INTEGER NOT NULL DEFAULT 1,
            unit_price    REAL NOT NULL DEFAULT 0,
            subtotal      REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS payments (
            payment_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id      INTEGER NOT NULL,
            amount        REAL NOT NULL,
            payment_date  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            notes         TEXT,
            FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS price_catalogue (
            item_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name      TEXT NOT NULL UNIQUE,
            price_coloured REAL,
            price_white    REAL,
            price_pressing REAL,
            updated_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        -- New table for customer ledger (Feature 1a)
        CREATE TABLE IF NOT EXISTS customer_ledger (
            ledger_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id    INTEGER NOT NULL,
            order_id       INTEGER,
            entry_type     TEXT NOT NULL CHECK(entry_type IN ('charge', 'payment', 'adjustment')),
            amount         REAL NOT NULL,
            running_balance REAL NOT NULL DEFAULT 0,
            notes          TEXT,
            entry_date     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE,
            FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
        CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
        CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
        CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_id);
        CREATE INDEX IF NOT EXISTS idx_price_catalogue_item ON price_catalogue(item_name);
        CREATE INDEX IF NOT EXISTS idx_ledger_customer ON customer_ledger(customer_id);
        CREATE INDEX IF NOT EXISTS idx_ledger_order ON customer_ledger(order_id);

        COMMIT;
        """
    )
    conn.commit()
    
    add_customer_type_column(conn)
    
    conn.close()


def migrate_ledger_from_existing_data(db_path: Optional[str] = None) -> None:
    """
    One-time migration to populate customer_ledger from existing orders and payments.
    Idempotent - runs only if ledger is empty.
    Wrapped in a transaction - all or nothing.
    (Feature 1b)
    """
    db_path = db_path or get_db_path()
    conn = connect_db(db_path)
    cur = conn.cursor()
    
    # Check if ledger is empty
    cur.execute("SELECT COUNT(*) as count FROM customer_ledger")
    if cur.fetchone()["count"] > 0:
        conn.close()
        print("Ledger already populated, skipping migration.")
        return
    
    try:
        cur.execute("BEGIN TRANSACTION")
        
        charge_count = 0
        payment_count = 0
        
        # Get all customers
        cur.execute("SELECT customer_id FROM customers ORDER BY customer_id")
        customers = cur.fetchall()
        
        for cust in customers:
            customer_id = cust["customer_id"]
            running_balance = 0.0
            
            # Get all finalised orders for this customer (total_amount > 0)
            cur.execute(
                """
                SELECT order_id, order_date, total_amount 
                FROM orders 
                WHERE customer_id = ? AND total_amount > 0 
                ORDER BY order_date ASC
                """,
                (customer_id,)
            )
            orders = cur.fetchall()
            
            for order in orders:
                # Insert charge entry
                running_balance += float(order["total_amount"])
                cur.execute(
                    """
                    INSERT INTO customer_ledger 
                    (customer_id, order_id, entry_type, amount, running_balance, entry_date)
                    VALUES (?, ?, 'charge', ?, ?, ?)
                    """,
                    (customer_id, order["order_id"], float(order["total_amount"]), 
                     running_balance, order["order_date"])
                )
                charge_count += 1
            
            # Get all payments for this customer
            cur.execute(
                """
                SELECT p.payment_id, p.order_id, p.amount, p.payment_date, o.customer_id
                FROM payments p
                JOIN orders o ON p.order_id = o.order_id
                WHERE o.customer_id = ?
                ORDER BY p.payment_date ASC
                """,
                (customer_id,)
            )
            payments = cur.fetchall()
            
            for payment in payments:
                # Insert payment entry (negative amount)
                running_balance -= float(payment["amount"])
                cur.execute(
                    """
                    INSERT INTO customer_ledger 
                    (customer_id, order_id, entry_type, amount, running_balance, notes, entry_date)
                    VALUES (?, ?, 'payment', ?, ?, ?, ?)
                    """,
                    (customer_id, payment["order_id"], -float(payment["amount"]),
                     running_balance, f"Payment ID: {payment['payment_id']}", payment["payment_date"])
                )
                payment_count += 1
        
        cur.execute("COMMIT")
        print(f"Ledger migration complete: {charge_count} charges, {payment_count} payments.")
        
    except Exception as e:
        cur.execute("ROLLBACK")
        print(f"Ledger migration failed: {e}")
        raise
    finally:
        conn.close()


def seed_price_catalogue(db_path: Optional[str] = None) -> None:
    """
    Seed the price_catalogue table with data from pricing.py if table is empty.
    """
    db_path = db_path or get_db_path()
    conn = connect_db(db_path)
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) as count FROM price_catalogue")
    count = cur.fetchone()["count"]
    
    if count == 0:
        for item in pricing.PRICE_CATALOGUE:
            cur.execute(
                """
                INSERT INTO price_catalogue (item_name, price_coloured, price_white, price_pressing)
                VALUES (?, ?, ?, ?)
                """,
                (item["item_name"], item["price_coloured"], item["price_white"], item["price_pressing"])
            )
        conn.commit()
        print(f"Seeded price catalogue with {len(pricing.PRICE_CATALOGUE)} items")
    
    conn.close()


def seed_admin(username: str = "admin", password: str = "admin123", role: str = "admin") -> Tuple[bool, str]:
    """
    Seed a default admin user if it does not already exist.
    """
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    if row:
        conn.close()
        return False, f"User '{username}' already exists (user_id={row['user_id']})."

    password_hash = hash_password(password)
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, role),
        )
        conn.commit()
        user_id = cur.lastrowid
        conn.close()
        return True, f"Seeded user '{username}' with user_id={user_id}."
    except sqlite3.IntegrityError as e:
        conn.close()
        return False, f"Failed to seed admin user: {e}"


def get_user_by_username(username: str) -> Optional[sqlite3.Row]:
    """
    Convenience helper to fetch user row by username.
    """
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row


if __name__ == "__main__":
    print(f"Initializing database at: {get_db_path()}")
    init_db(force=False)
    created, msg = seed_admin()
    print(msg)
    seed_price_catalogue()
    migrate_ledger_from_existing_data()
    admin_row = get_user_by_username("admin")
    if admin_row:
        print("Admin user present. Username:", admin_row["username"], "Role:", admin_row["role"])
    else:
        print("Admin user not found — something went wrong.")
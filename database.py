#!/usr/bin/env python3
"""
database.py

Initializes the SQLite database for the Laundry Management System (LMS).

Responsibilities:
- Create lms.db (by default) if absent
- Create tables per project schema:
    users, customers, orders, order_items, payments
- Seed a default admin user (username: admin, password: admin123)
- Provide helper functions to connect to the DB and hash/verify passwords

Notes / decisions:
- To distinguish discount types (percent vs fixed) I've added orders.discount_type TEXT.
  This is safer than encoding the type into a single numeric column.
- Password hashing uses PBKDF2-HMAC-SHA256 (built-in, secure for our scope).
  The password_hash column stores: iterations$salt_hex$hash_hex
- The DB file path can be overridden using the LMS_DB_PATH environment variable.

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

# Default DB filename (can be overridden with LMS_DB_PATH env var)
DEFAULT_DB = os.environ.get("LMS_DB_PATH", "lms.db")

# PBKDF2 configuration
PBKDF2_ITERATIONS = 100_000  # strong default for desktop app


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
    # Turn on foreign key enforcement
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    """
    Hash the password using PBKDF2-HMAC-SHA256.
    Stored format: iterations$salt_hex$hash_hex

    We generate a 16-byte salt using secrets.token_bytes for good entropy.
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
        # Stored value malformed
        return False

    dk = hashlib.pbkdf2_hmac("sha256", provided_password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(dk, expected)


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

    # Use TEXT for timestamps with default CURRENT_TIMESTAMP for simplicity.
    # Numeric fields: REAL for amounts (to support decimals), INTEGER for PKs/quantities.
    # Note: We add orders.discount_type TEXT to indicate 'percent' or 'fixed'.
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
            discount              REAL DEFAULT 0,     -- numeric discount value
            discount_type         TEXT DEFAULT 'fixed',  -- 'percent' or 'fixed'
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

        -- Helpful indexes for common lookups
        CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
        CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
        CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
        CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_id);

        COMMIT;
        """
    )
    conn.commit()
    conn.close()


def seed_admin(username: str = "admin", password: str = "admin123", role: str = "admin") -> Tuple[bool, str]:
    """
    Seed a default admin user if it does not already exist.
    Returns (created, message).
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
    Returns sqlite3.Row or None.
    """
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row


if __name__ == "__main__":
    # Initialize DB and seed admin. Useful for local development/testing.
    print(f"Initializing database at: {get_db_path()}")
    init_db(force=False)
    created, msg = seed_admin()
    print(msg)
    # Quick verification sample
    admin_row = get_user_by_username("admin")
    if admin_row:
        print("Admin user present. Username:", admin_row["username"], "Role:", admin_row["role"])
    else:
        print("Admin user not found — something went wrong.")
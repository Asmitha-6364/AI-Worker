"""
SQLite Database interface for AcmeOps.
"""

import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
from config import DB_PATH, ACME_ADMIN_USERNAME, ACME_ADMIN_PASSWORD


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(force_reset: bool = False):
    """Initialize database tables and seed default users/invoices."""
    with get_connection() as conn:
        cursor = conn.cursor()

        if force_reset:
            cursor.execute("DROP TABLE IF EXISTS audit_logs")
            cursor.execute("DROP TABLE IF EXISTS invoices")
            cursor.execute("DROP TABLE IF EXISTS system_flags")
            cursor.execute("DROP TABLE IF EXISTS users")
            conn.commit()

        # Users table

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'accountant',
                created_at TEXT NOT NULL
            )
        """)

        # Invoices table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor TEXT NOT NULL,
                invoice_number TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                due_date TEXT NOT NULL,
                issue_date TEXT,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'PENDING',
                source_channel TEXT NOT NULL DEFAULT 'WEB_UI',
                created_at TEXT NOT NULL,
                verified INTEGER NOT NULL DEFAULT 0,
                UNIQUE(vendor, invoice_number)
            )
        """)

        # Audit log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                details TEXT NOT NULL,
                user TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)

        # Failure mode control table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_flags (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Seed admin user if not exists
        cursor.execute("SELECT id FROM users WHERE username = ?", (ACME_ADMIN_USERNAME,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, ?)",
                (ACME_ADMIN_USERNAME, ACME_ADMIN_PASSWORD, "admin", datetime.utcnow().isoformat())
            )

        # Set default system flags
        cursor.execute("INSERT OR IGNORE INTO system_flags (key, value) VALUES ('flaky_ui_submit', '0')")

        conn.commit()


def get_flag(key: str, default: str = "0") -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_flags WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default


def set_flag(key: str, value: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO system_flags (key, value) VALUES (?, ?)", (key, value))
        conn.commit()


def create_invoice(
    vendor: str,
    invoice_number: str,
    amount: float,
    currency: str,
    due_date: str,
    issue_date: Optional[str] = None,
    description: str = "",
    source_channel: str = "WEB_UI"
) -> Dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute(
            """
            INSERT INTO invoices (vendor, invoice_number, amount, currency, due_date, issue_date, description, status, source_channel, created_at, verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, 0)
            """,
            (vendor, invoice_number, amount, currency, due_date, issue_date, description, source_channel, now)
        )
        invoice_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO audit_logs (action, details, user, timestamp) VALUES (?, ?, ?, ?)",
            ("RECORD_INVOICE", f"Created invoice #{invoice_id} ({invoice_number}) from {vendor} for {amount} {currency} via {source_channel}", "system", now)
        )
        conn.commit()

        cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
        row = cursor.fetchone()
        return dict(row)


def list_invoices(vendor_filter: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM invoices"
        params = []
        conditions = []

        if vendor_filter:
            conditions.append("vendor LIKE ?")
            params.append(f"%{vendor_filter}%")
        if search:
            conditions.append("(vendor LIKE ? OR invoice_number LIKE ? OR description LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY id DESC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_invoice_by_id(invoice_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_invoice_by_vendor_and_number(vendor: str, invoice_number: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM invoices WHERE LOWER(vendor) = LOWER(?) AND LOWER(invoice_number) = LOWER(?)", (vendor.strip(), invoice_number.strip()))
        row = cursor.fetchone()
        return dict(row) if row else None


def mark_invoice_verified(invoice_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE invoices SET verified = 1 WHERE id = ?", (invoice_id,))
        conn.commit()
        return cursor.rowcount > 0


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, role FROM users WHERE username = ? AND password = ?", (username, password))
        row = cursor.fetchone()
        return dict(row) if row else None

"""Centralized SQLite helper to eliminate duplicated boilerplate."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager


class SQLiteHelper:
    """Thin wrapper around sqlite3 with WAL mode, row_factory, and safe connections."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    def conn(self) -> sqlite3.Connection:
        """Return a new connection with row_factory and WAL mode."""
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    @contextmanager
    def connection(self):
        """Context manager that guarantees connection is closed."""
        c = self.conn()
        try:
            yield c
        finally:
            c.close()

    def execute(self, sql: str, params=None) -> list:
        """Execute a read query and return all rows."""
        with self.connection() as c:
            return c.execute(sql, params or ()).fetchall()

    def execute_write(self, sql: str, params=None):
        """Execute a write query and commit."""
        with self.connection() as c:
            c.execute(sql, params or ())
            c.commit()

    def executescript(self, sql: str):
        """Execute a multi-statement script."""
        with self.connection() as c:
            c.executescript(sql)
            c.commit()

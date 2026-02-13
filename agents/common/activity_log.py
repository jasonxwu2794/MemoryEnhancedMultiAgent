"""Unified activity log for all agent actions via SQLite."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Optional

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    agent TEXT NOT NULL,
    action_type TEXT NOT NULL,
    description TEXT,
    task_id TEXT,
    project_id TEXT,
    feature_id TEXT,
    metadata JSON,
    success BOOLEAN DEFAULT 1
);
"""


class ActivityLog:
    """SQLite-backed unified log of every agent action."""

    def __init__(self, db_path: str = "data/activity.db"):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._conn()
        conn.execute(_CREATE_TABLE)
        conn.commit()
        conn.close()

    def log(
        self,
        agent: str,
        action_type: str,
        description: str,
        task_id: Optional[str] = None,
        project_id: Optional[str] = None,
        feature_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        success: bool = True,
    ):
        meta_json = json.dumps(metadata) if metadata else None
        with self._lock:
            conn = self._conn()
            conn.execute(
                "INSERT INTO activity (agent, action_type, description, task_id, "
                "project_id, feature_id, metadata, success) VALUES (?,?,?,?,?,?,?,?)",
                (agent, action_type, description, task_id, project_id, feature_id, meta_json, success),
            )
            conn.commit()
            conn.close()

    def get_recent(self, limit: int = 50, agent: Optional[str] = None) -> list[dict]:
        conn = self._conn()
        if agent:
            rows = conn.execute(
                "SELECT * FROM activity WHERE agent=? ORDER BY id DESC LIMIT ?",
                (agent, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        conn.close()
        return [self._row_to_dict(r) for r in rows]

    def get_project_activity(self, project_id: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM activity WHERE project_id=? ORDER BY id ASC", (project_id,)
        ).fetchall()
        conn.close()
        return [self._row_to_dict(r) for r in rows]

    def get_timeline(self, hours: int = 24) -> list[dict]:
        since = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM activity WHERE timestamp>=? ORDER BY id ASC", (since,)
        ).fetchall()
        conn.close()
        return [self._row_to_dict(r) for r in rows]

    def get_summary(self, days: int = 7) -> dict:
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        conn = self._conn()
        rows = conn.execute(
            "SELECT agent, action_type, COUNT(*) as cnt FROM activity "
            "WHERE date(timestamp)>=? GROUP BY agent, action_type",
            (since,),
        ).fetchall()
        conn.close()
        summary: dict[str, dict[str, int]] = {}
        for r in rows:
            summary.setdefault(r["agent"], {})[r["action_type"]] = r["cnt"]
        return {"days": days, "per_agent": summary}

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        if d.get("metadata"):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

"""Persistent usage tracking for all LLM API calls via SQLite."""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Optional

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS api_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    agent TEXT NOT NULL,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cost_estimate REAL DEFAULT 0.0,
    task_id TEXT,
    project_id TEXT,
    duration_ms INTEGER,
    success BOOLEAN DEFAULT 1,
    error_message TEXT
);
"""

# Rough cost per 1M tokens (input, output) in USD
COST_TABLE: dict[str, tuple[float, float]] = {
    "claude-sonnet": (3.0, 15.0),
    "claude-opus": (15.0, 75.0),
    "deepseek": (0.14, 0.28),
    "qwen": (1.6, 6.4),
    "minimax": (0.5, 1.5),
    "kimi": (1.0, 3.0),
    "moonshot": (1.0, 3.0),
    "mistral": (0.3, 0.9),
    "codestral": (0.3, 0.9),
}


def _match_cost_key(model: str, provider: str) -> str:
    model_lower = model.lower()
    for key in COST_TABLE:
        if key in model_lower or key in provider.lower():
            return key
    return "deepseek"  # cheapest default


class UsageTracker:
    """SQLite-backed persistent tracking of every LLM API call."""

    def __init__(self, db_path: str = "data/usage.db"):
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

    @staticmethod
    def estimate_cost(model: str, provider: str, input_tokens: int, output_tokens: int) -> float:
        key = _match_cost_key(model, provider)
        inp_rate, out_rate = COST_TABLE.get(key, (1.0, 3.0))
        return (input_tokens * inp_rate + output_tokens * out_rate) / 1_000_000

    def log_call(
        self,
        agent: str,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        cost_estimate: Optional[float] = None,
        task_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        project_id: Optional[str] = None,
    ):
        if cost_estimate is None:
            cost_estimate = self.estimate_cost(model, provider, input_tokens, output_tokens)
        total_tokens = input_tokens + output_tokens
        with self._lock:
            conn = self._conn()
            conn.execute(
                "INSERT INTO api_calls (agent, model, provider, input_tokens, output_tokens, "
                "total_tokens, cost_estimate, task_id, project_id, duration_ms, success, error_message) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (agent, model, provider, input_tokens, output_tokens, total_tokens,
                 cost_estimate, task_id, project_id, duration_ms, success, error_message),
            )
            conn.commit()
            conn.close()

    def get_daily_summary(self, date: Optional[str] = None) -> dict:
        date = date or datetime.utcnow().strftime("%Y-%m-%d")
        conn = self._conn()
        rows = conn.execute(
            "SELECT agent, COUNT(*) as calls, SUM(input_tokens) as inp, "
            "SUM(output_tokens) as out, SUM(total_tokens) as total, SUM(cost_estimate) as cost "
            "FROM api_calls WHERE date(timestamp)=? GROUP BY agent",
            (date,),
        ).fetchall()
        conn.close()
        per_agent = {r["agent"]: {"calls": r["calls"], "input_tokens": r["inp"] or 0,
                                   "output_tokens": r["out"] or 0, "total_tokens": r["total"] or 0,
                                   "cost": r["cost"] or 0.0} for r in rows}
        return {
            "date": date,
            "per_agent": per_agent,
            "total_tokens": sum(v["total_tokens"] for v in per_agent.values()),
            "total_cost": sum(v["cost"] for v in per_agent.values()),
            "total_calls": sum(v["calls"] for v in per_agent.values()),
        }

    def get_agent_summary(self, agent: str, days: int = 30) -> dict:
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) as calls, SUM(input_tokens) as inp, SUM(output_tokens) as out, "
            "SUM(total_tokens) as total, SUM(cost_estimate) as cost, AVG(duration_ms) as avg_dur "
            "FROM api_calls WHERE agent=? AND date(timestamp)>=?",
            (agent, since),
        ).fetchone()
        conn.close()
        return {
            "agent": agent,
            "days": days,
            "calls": row["calls"] or 0,
            "input_tokens": row["inp"] or 0,
            "output_tokens": row["out"] or 0,
            "total_tokens": row["total"] or 0,
            "cost": row["cost"] or 0.0,
            "avg_duration_ms": round(row["avg_dur"] or 0),
        }

    def get_model_summary(self, days: int = 30) -> dict:
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        conn = self._conn()
        rows = conn.execute(
            "SELECT model, provider, COUNT(*) as calls, SUM(total_tokens) as total, "
            "SUM(cost_estimate) as cost FROM api_calls WHERE date(timestamp)>=? "
            "GROUP BY model, provider ORDER BY cost DESC",
            (since,),
        ).fetchall()
        conn.close()
        return {
            "days": days,
            "models": [{"model": r["model"], "provider": r["provider"], "calls": r["calls"],
                         "total_tokens": r["total"] or 0, "cost": r["cost"] or 0.0} for r in rows],
        }

    def get_total_cost(self, days: int = 30) -> float:
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        conn = self._conn()
        row = conn.execute(
            "SELECT SUM(cost_estimate) as cost FROM api_calls WHERE date(timestamp)>=?",
            (since,),
        ).fetchone()
        conn.close()
        return row["cost"] or 0.0

    def get_cost_report(self) -> str:
        today = self.get_daily_summary()
        month = self.get_model_summary(days=30)
        total_30d = self.get_total_cost(days=30)

        lines = [
            "=== Cost Report ===",
            f"Today: {today['total_calls']} calls, {today['total_tokens']:,} tokens, ${today['total_cost']:.4f}",
        ]
        if today["per_agent"]:
            for agent, stats in today["per_agent"].items():
                lines.append(f"  {agent}: {stats['calls']} calls, ${stats['cost']:.4f}")
        lines.append(f"\n30-day total: ${total_30d:.4f}")
        if month["models"]:
            lines.append("Top models (30d):")
            for m in month["models"][:5]:
                lines.append(f"  {m['model']} ({m['provider']}): {m['calls']} calls, ${m['cost']:.4f}")
        return "\n".join(lines)

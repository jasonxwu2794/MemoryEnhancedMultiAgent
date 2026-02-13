"""Knowledge cache operations for verified facts."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

import numpy as np

from memory.embeddings import cosine_similarity, deserialize_embedding, serialize_embedding


def store_fact(
    fact: str,
    embedding: np.ndarray,
    source_agent: str,
    confidence: float,
    db: sqlite3.Connection,
    metadata: dict | None = None,
) -> str:
    """Store a verified fact in the knowledge cache. Returns fact id."""
    fact_id = f"fact_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO knowledge_cache (id, fact, embedding, source, verified_by, verified_at, confidence, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (fact_id, fact, serialize_embedding(embedding), source_agent, source_agent, now, confidence,
         str(metadata or {})),
    )
    db.commit()
    return fact_id


def lookup_facts(
    query_embedding: np.ndarray,
    db: sqlite3.Connection,
    limit: int = 5,
) -> list[dict]:
    """Retrieve matching facts from the knowledge cache by embedding similarity."""
    rows = db.execute("SELECT id, fact, embedding, confidence, metadata FROM knowledge_cache").fetchall()

    scored: list[tuple[float, dict]] = []
    for row in rows:
        if row["embedding"] is None:
            continue
        emb = deserialize_embedding(row["embedding"])
        sim = cosine_similarity(query_embedding, emb)
        scored.append((sim, {
            "id": row["id"],
            "fact": row["fact"],
            "confidence": row["confidence"],
            "similarity": sim,
        }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


def update_confidence(fact_id: str, new_confidence: float, db: sqlite3.Connection) -> None:
    """Update the confidence of a fact."""
    db.execute(
        "UPDATE knowledge_cache SET confidence = ? WHERE id = ?",
        (new_confidence, fact_id),
    )
    db.commit()

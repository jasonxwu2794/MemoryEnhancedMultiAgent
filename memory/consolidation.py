"""Background consolidation job for memory maintenance."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone, timedelta

import numpy as np

from memory.embeddings import cosine_similarity, deserialize_embedding, serialize_embedding


def run_consolidation(db: sqlite3.Connection, tier: str = "full") -> int:
    """Main consolidation routine. Returns number of memories consolidated."""
    old = find_old_memories(db)
    if not old:
        return 0

    clusters = cluster_memories(old)
    consolidated = 0
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        summary = summarize_cluster(cluster)
        # Store consolidated memory as long-term
        summary_id = f"mem_{uuid.uuid4().hex[:12]}"
        best = max(cluster, key=lambda m: m["importance"])
        db.execute(
            "INSERT INTO memories (id, content, embedding, tier, importance, tags, source_agent, metadata) "
            "VALUES (?, ?, ?, 'long_term', ?, ?, ?, ?)",
            (summary_id, summary, best["embedding"], best["importance"],
             best["tags"], best["source_agent"], str({"consolidated_from": [m["id"] for m in cluster]})),
        )
        # Link originals and mark them
        for mem in cluster:
            db.execute(
                "INSERT OR IGNORE INTO memory_links (memory_id_a, memory_id_b, relation_type, strength) "
                "VALUES (?, ?, 'consolidated_into', 1.0)",
                (mem["id"], summary_id),
            )
            db.execute("DELETE FROM memories WHERE id = ?", (mem["id"],))
        consolidated += len(cluster)

    if tier != "full":
        consolidated += prune_low_importance(db)

    db.commit()
    return consolidated


def find_old_memories(db: sqlite3.Connection, days: int = 7) -> list[dict]:
    """Find short-term memories older than `days`."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = db.execute(
        "SELECT id, content, embedding, importance, tags, source_agent FROM memories "
        "WHERE tier = 'short_term' AND created_at < ?",
        (cutoff,),
    ).fetchall()
    return [dict(r) for r in rows]


def cluster_memories(memories: list[dict], threshold: float = 0.7) -> list[list[dict]]:
    """Group memories by embedding similarity (simple greedy clustering)."""
    if not memories:
        return []

    used = set()
    clusters: list[list[dict]] = []

    for i, mem in enumerate(memories):
        if i in used or mem["embedding"] is None:
            continue
        cluster = [mem]
        used.add(i)
        emb_i = deserialize_embedding(mem["embedding"])
        for j in range(i + 1, len(memories)):
            if j in used or memories[j]["embedding"] is None:
                continue
            emb_j = deserialize_embedding(memories[j]["embedding"])
            if cosine_similarity(emb_i, emb_j) >= threshold:
                cluster.append(memories[j])
                used.add(j)
        clusters.append(cluster)

    return clusters


def summarize_cluster(cluster: list[dict]) -> str:
    """Summarize a cluster of memories.
    
    TODO: Use LLM for real summarization. For now, pick highest importance memory.
    """
    best = max(cluster, key=lambda m: m.get("importance", 0))
    return best["content"]


def prune_low_importance(db: sqlite3.Connection, threshold: float = 0.3) -> int:
    """Remove low-importance short-term memories (Standard tier)."""
    cursor = db.execute(
        "DELETE FROM memories WHERE tier = 'short_term' AND importance < ?",
        (threshold,),
    )
    return cursor.rowcount

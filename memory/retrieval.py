"""Retrieval with knowledge graph traversal and context budgeting."""

from __future__ import annotations

import json
import logging
import sqlite3

import numpy as np

logger = logging.getLogger(__name__)

from memory.embeddings import cosine_similarity, deserialize_embedding
from memory.scoring import compute_recency_score, compute_composite_score


def retrieve_memories(
    query_embedding: np.ndarray,
    db: sqlite3.Connection,
    strategy: str = "balanced",
    limit: int = 5,
    tags: list[str] | None = None,
) -> list[dict]:
    """Main retrieval: score all memories and return top matches."""
    query = "SELECT id, content, embedding, tier, importance, tags, created_at, access_count, source_agent, metadata FROM memories"
    params: list = []

    if tags:
        # Filter by any matching tag
        tag_clauses = " OR ".join(["tags LIKE ?" for _ in tags])
        query += f" WHERE ({tag_clauses})"
        params = [f"%{t}%" for t in tags]

    rows = db.execute(query, params).fetchall()

    scored: list[tuple[float, dict]] = []
    for row in rows:
        if row["embedding"] is None:
            continue
        try:
            emb = deserialize_embedding(row["embedding"])
            semantic_sim = cosine_similarity(query_embedding, emb)
        except Exception as e:
            logger.warning(f"Failed to deserialize/compare embedding for {row['id']}: {e}")
            continue
        recency = compute_recency_score(row["created_at"])
        importance = row["importance"]
        score = compute_composite_score(semantic_sim, recency, importance, strategy)

        # Handle metadata gracefully
        metadata = {}
        try:
            raw_meta = row["metadata"]
            if raw_meta and isinstance(raw_meta, str):
                metadata = json.loads(raw_meta)
        except (json.JSONDecodeError, TypeError, IndexError, KeyError):
            metadata = {}

        scored.append((score, {
            "id": row["id"],
            "content": row["content"],
            "tier": row["tier"],
            "importance": importance,
            "tags": row["tags"],
            "created_at": row["created_at"],
            "score": score,
            "semantic_similarity": semantic_sim,
            "source_agent": row["source_agent"],
            "metadata": metadata,
        }))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Update access counts for retrieved memories
    results = [item for _, item in scored[:limit]]
    for mem in results:
        db.execute(
            "UPDATE memories SET access_count = access_count + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (mem["id"],),
        )
    db.commit()

    return results


def follow_links(memory_id: str, db: sqlite3.Connection, depth: int = 1) -> list[dict]:
    """Traverse knowledge graph links from a memory."""
    visited: set[str] = {memory_id}
    results: list[dict] = []
    frontier = [memory_id]

    for _ in range(depth):
        next_frontier: list[str] = []
        for mid in frontier:
            rows = db.execute(
                "SELECT memory_id_a, memory_id_b, relation_type, strength "
                "FROM memory_links WHERE memory_id_a = ? OR memory_id_b = ?",
                (mid, mid),
            ).fetchall()
            for row in rows:
                linked_id = row["memory_id_b"] if row["memory_id_a"] == mid else row["memory_id_a"]
                if linked_id in visited:
                    continue
                visited.add(linked_id)
                next_frontier.append(linked_id)
                # Fetch the linked memory
                mem = db.execute("SELECT id, content, importance, tags FROM memories WHERE id = ?", (linked_id,)).fetchone()
                if mem:
                    results.append({
                        **dict(mem),
                        "relation": row["relation_type"],
                        "link_strength": row["strength"],
                    })
        frontier = next_frontier

    return results


def apply_context_budget(memories: list[dict], budget_tokens: int) -> list[dict]:
    """Trim memories to fit within a token budget (rough: 1 token ≈ 0.75 words)."""
    selected: list[dict] = []
    used = 0
    for mem in memories:
        # Rough token estimate
        tokens = int(len(mem["content"].split()) / 0.75)
        if used + tokens > budget_tokens:
            break
        selected.append(mem)
        used += tokens
    return selected

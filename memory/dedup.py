"""Deduplication logic for memory ingestion."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum

import numpy as np

from memory.embeddings import cosine_similarity


class MatchType(Enum):
    EXACT_DUP = "exact_dup"   # > 0.92
    RELATED = "related"        # 0.7 – 0.92
    NOVEL = "novel"            # < 0.7


@dataclass
class DedupResult:
    match_type: MatchType
    matched_id: str | None = None
    similarity: float = 0.0


def check_duplicate(
    embedding: np.ndarray,
    existing: list[tuple[str, np.ndarray]],
) -> DedupResult:
    """Check a new embedding against existing ones. Returns best match info."""
    best_sim = 0.0
    best_id: str | None = None
    for mem_id, existing_emb in existing:
        sim = cosine_similarity(embedding, existing_emb)
        if sim > best_sim:
            best_sim = sim
            best_id = mem_id

    if best_sim > 0.92:
        return DedupResult(MatchType.EXACT_DUP, best_id, best_sim)
    elif best_sim > 0.7:
        return DedupResult(MatchType.RELATED, best_id, best_sim)
    else:
        return DedupResult(MatchType.NOVEL, None, best_sim)


def handle_duplicate(
    memory_id: str,
    match_type: MatchType,
    matched_id: str | None,
    db: sqlite3.Connection,
) -> bool:
    """Handle dedup result. Returns True if the new memory should be stored."""
    match match_type:
        case MatchType.EXACT_DUP:
            # Boost existing memory importance instead of storing duplicate
            if matched_id:
                db.execute(
                    "UPDATE memories SET importance = MIN(importance + 0.1, 1.0), "
                    "updated_at = CURRENT_TIMESTAMP, access_count = access_count + 1 "
                    "WHERE id = ?",
                    (matched_id,),
                )
                db.commit()
            return False

        case MatchType.RELATED:
            # Store new memory and create a link to the related one
            if matched_id:
                db.execute(
                    "INSERT OR IGNORE INTO memory_links (memory_id_a, memory_id_b, relation_type, strength) "
                    "VALUES (?, ?, 'related_to', ?)",
                    (memory_id, matched_id, 0.8),
                )
                db.commit()
            return True

        case MatchType.NOVEL:
            return True

"""Turn processing and chunking for memory ingestion."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Chunk:
    id: str
    content: str
    chunk_type: str  # "user_query" or "agent_response"
    turn_id: str
    chunk_index: int = 0
    total_chunks: int = 1
    metadata: dict = field(default_factory=dict)


def split_turn(
    user_message: str,
    agent_response: str,
    turn_id: str | None = None,
) -> list[Chunk]:
    """Split a conversation turn into separate user and response chunks."""
    turn_id = turn_id or f"turn_{uuid.uuid4().hex[:8]}"

    chunks: list[Chunk] = []

    # User message is always one chunk
    chunks.append(Chunk(
        id=f"mem_{uuid.uuid4().hex[:12]}",
        content=user_message,
        chunk_type="user_query",
        turn_id=turn_id,
    ))

    # Agent response may be chunked if long
    response_chunks = chunk_response(agent_response)
    total = len(response_chunks)
    for i, text in enumerate(response_chunks):
        chunks.append(Chunk(
            id=f"mem_{uuid.uuid4().hex[:12]}",
            content=text,
            chunk_type="agent_response",
            turn_id=turn_id,
            chunk_index=i,
            total_chunks=total,
        ))

    return chunks


def chunk_response(response_text: str, threshold: int = 200) -> list[str]:
    """Split a long response by topic boundaries (heuristic).
    
    If under threshold tokens (~words as proxy), return as-is.
    Otherwise split on markdown headers or double newlines.
    
    TODO: Replace heuristic with LLM-based topic boundary detection.
    """
    # Rough token estimate: words ≈ tokens * 0.75
    word_count = len(response_text.split())
    if word_count < threshold:
        return [response_text]

    # Split on markdown headers or double newlines
    parts = re.split(r'\n(?=#{1,3}\s)|\n\n+', response_text)
    parts = [p.strip() for p in parts if p.strip()]

    # Merge very small chunks (< 30 words) with their neighbor
    merged: list[str] = []
    for part in parts:
        if merged and len(merged[-1].split()) < 30:
            merged[-1] = merged[-1] + "\n\n" + part
        else:
            merged.append(part)

    return merged if merged else [response_text]


def stamp_metadata(
    chunk: Chunk,
    turn_id: str,
    agent: str = "brain",
    user: str = "user",
    tags: list[str] | None = None,
    sibling_ids: list[str] | None = None,
    linked_ids: dict[str, str] | None = None,
) -> Chunk:
    """Add rich metadata with bidirectional links to a chunk."""
    now = datetime.now(timezone.utc).isoformat()
    chunk.metadata = {
        "type": chunk.chunk_type,
        "timestamp": now,
        "turn_id": turn_id,
        "tags": tags or [],
        "links": linked_ids or {},
    }
    if chunk.chunk_type == "user_query":
        chunk.metadata["user"] = user
    else:
        chunk.metadata["agent"] = agent
        if chunk.total_chunks > 1:
            chunk.metadata["chunk"] = f"{chunk.chunk_index + 1}/{chunk.total_chunks}"
        if sibling_ids:
            chunk.metadata["links"]["siblings"] = sibling_ids

    return chunk

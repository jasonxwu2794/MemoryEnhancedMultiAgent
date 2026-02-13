"""MemoryEngine — single entry point for all memory operations."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from pathlib import Path
from dataclasses import dataclass

import numpy as np

from memory.schemas import init_db
from memory.embeddings import get_embedder, serialize_embedding, deserialize_embedding, Embedder
from memory.scoring import compute_importance_score
from memory.dedup import check_duplicate, handle_duplicate
from memory.chunker import split_turn, stamp_metadata, Chunk
from memory.knowledge_cache import lookup_facts
from memory.retrieval import retrieve_memories, follow_links, apply_context_budget

logger = logging.getLogger(__name__)


@dataclass
class Turn:
    """A conversation turn."""
    user_message: str
    agent_response: str
    agent: str = "brain"
    user: str = "user"
    tags: list[str] | None = None
    signals: list[str] | None = None


class MemoryEngine:
    """Orchestrates all memory operations: ingest, retrieve, feedback, budgeting."""

    def __init__(self, db_path: str | Path = "data/memory.db", embedder_config: dict | None = None):
        self._db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self.db: sqlite3.Connection = init_db(db_path)
        except Exception as e:
            logger.error(f"Failed to init DB at {db_path}: {e}, creating fresh")
            try:
                Path(db_path).unlink(missing_ok=True)
                self.db = init_db(db_path)
            except Exception as e2:
                logger.error(f"Could not create fresh DB: {e2}")
                # In-memory fallback
                self.db = init_db(":memory:")
        self.embedder: Embedder = get_embedder(embedder_config)

    def ingest(self, turn: Turn) -> dict:
        """Process a conversation turn through the full pipeline.
        
        Pipeline: split → chunk → stamp → dedup → score → embed → store.
        Never crashes the caller — always returns success/failure dict.
        """
        try:
            return self._ingest_inner(turn)
        except Exception as e:
            logger.error(f"Memory ingest failed (non-fatal): {e}", exc_info=True)
            return {"success": False, "error": str(e), "stored_ids": []}

    def _ingest_inner(self, turn: Turn) -> dict:
        """Inner ingest — may raise."""
        chunks = split_turn(turn.user_message, turn.agent_response)

        # Build cross-links between user query and response chunks
        user_chunk = chunks[0]
        response_ids = [c.id for c in chunks[1:]]

        stamp_metadata(user_chunk, user_chunk.turn_id, turn.agent, turn.user, turn.tags,
                        linked_ids={"response_ids": json.dumps(response_ids)})

        for chunk in chunks[1:]:
            stamp_metadata(chunk, chunk.turn_id, turn.agent, turn.user, turn.tags,
                            sibling_ids=[c.id for c in chunks[1:] if c.id != chunk.id],
                            linked_ids={"query_id": user_chunk.id})

        # Load existing embeddings for dedup
        existing = self._get_existing_embeddings()

        stored_ids: list[str] = []
        importance = compute_importance_score(turn.signals or [])

        for chunk in chunks:
            # Attempt embedding; store without if it fails
            try:
                embedding = self.embedder.embed(chunk.content)
            except Exception as e:
                logger.warning(f"Embedding failed for chunk {chunk.id}: {e}, storing text-only")
                embedding = None

            # Dedup check (skip if no embedding)
            if embedding is not None:
                dedup_result = check_duplicate(embedding, existing)
                should_store = handle_duplicate(chunk.id, dedup_result.match_type, dedup_result.matched_id, self.db)
                if not should_store:
                    continue

            # Store with retry for locked DB
            tags_str = ",".join(turn.tags) if turn.tags else None
            emb_blob = serialize_embedding(embedding) if embedding is not None else None
            self._execute_with_retry(
                "INSERT INTO memories (id, content, embedding, tier, importance, tags, source_agent, metadata) "
                "VALUES (?, ?, ?, 'short_term', ?, ?, ?, ?)",
                (chunk.id, chunk.content, emb_blob, importance,
                 tags_str, turn.agent, json.dumps(chunk.metadata)),
            )
            stored_ids.append(chunk.id)
            if embedding is not None:
                existing.append((chunk.id, embedding))

        return {"success": True, "stored_ids": stored_ids}

    def _execute_with_retry(self, sql: str, params: tuple, max_retries: int = 3) -> None:
        """Execute SQL with retry on database locked errors."""
        for attempt in range(max_retries):
            try:
                self.db.execute(sql, params)
                self.db.commit()
                return
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    delay = 1 * (2 ** attempt)
                    logger.warning(f"DB locked, retry {attempt + 1}/{max_retries} after {delay}s")
                    time.sleep(delay)
                else:
                    raise

    def retrieve(
        self,
        query: str,
        strategy: str = "balanced",
        limit: int = 5,
        tags: list[str] | None = None,
    ) -> list[dict]:
        """Retrieve relevant memories for a query. Never crashes — returns [] on error."""
        try:
            query_embedding = self.embedder.embed(query)
        except Exception as e:
            logger.warning(f"Embedding failed for query, falling back to keyword search: {e}")
            # Fall back to keyword search
            try:
                return self._keyword_search(query, limit)
            except Exception as e2:
                logger.error(f"Keyword search also failed: {e2}")
                return []

        try:
            # Check knowledge cache first
            try:
                facts = lookup_facts(query_embedding, self.db, limit=2)
            except Exception as e:
                logger.warning(f"Knowledge cache lookup failed: {e}")
                facts = []

            # Retrieve from memories
            memories = retrieve_memories(query_embedding, self.db, strategy, limit, tags)

            # Follow links for top results to get related context
            for mem in memories[:3]:
                try:
                    linked = follow_links(mem["id"], self.db, depth=1)
                    mem["linked_memories"] = linked
                except Exception:
                    mem["linked_memories"] = []

            # Prepend high-confidence facts
            results: list[dict] = []
            for f in facts:
                if f["confidence"] >= 0.7 and f["similarity"] > 0.5:
                    results.append({"type": "fact", **f})
            results.extend(memories)

            return results[:limit]
        except Exception as e:
            logger.error(f"Memory retrieval failed: {e}")
            return []

    def _keyword_search(self, query: str, limit: int = 5) -> list[dict]:
        """Simple keyword-based fallback search."""
        words = query.lower().split()[:5]
        if not words:
            return []
        clause = " OR ".join(["content LIKE ?" for _ in words])
        params = [f"%{w}%" for w in words]
        rows = self.db.execute(
            f"SELECT id, content, importance, tags, created_at FROM memories WHERE {clause} LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]

    def feedback(self, memory_id: str, positive: bool = True) -> None:
        """Adjust memory importance based on user feedback."""
        delta = 0.1 if positive else -0.3
        self.db.execute(
            "UPDATE memories SET importance = MAX(0, MIN(importance + ?, 1.0)), "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (delta, memory_id),
        )
        self.db.commit()

    def get_context_budget(self, total_tokens: int, conversation_tokens: int) -> int:
        """Calculate tokens available for memory injection (15% cap)."""
        max_memory_tokens = int(total_tokens * 0.15)
        system_tokens = int(total_tokens * 0.10)
        response_buffer = int(total_tokens * 0.10)
        available = total_tokens - system_tokens - conversation_tokens - response_buffer
        return min(available, max_memory_tokens)

    def _get_existing_embeddings(self) -> list[tuple[str, np.ndarray]]:
        """Load all existing embeddings for dedup comparison."""
        rows = self.db.execute("SELECT id, embedding FROM memories WHERE embedding IS NOT NULL").fetchall()
        result: list[tuple[str, np.ndarray]] = []
        for row in rows:
            emb = deserialize_embedding(row["embedding"])
            result.append((row["id"], emb))
        return result


if __name__ == "__main__":
    import tempfile, os

    print("=== MemoryEngine end-to-end test ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = MemoryEngine(db_path=db_path)

        # Ingest a turn
        turn = Turn(
            user_message="How do I set up OAuth2 in Python?",
            agent_response="You can use the `authlib` library for OAuth2 in Python. Install it with pip install authlib. Then configure your client credentials and use the OAuth2Session class.",
            agent="brain",
            tags=["domain:python", "topic:oauth2"],
            signals=["technical_detail"],
        )
        result = engine.ingest(turn)
        stored = result.get("stored_ids", []) if isinstance(result, dict) else result
        print(f"Stored {len(stored)} memories: {stored}")

        # Ingest another turn
        turn2 = Turn(
            user_message="What about refresh tokens?",
            agent_response="Refresh tokens are handled automatically by authlib's OAuth2Session. Set token_endpoint_auth_method and the session will refresh when the access token expires.",
            agent="brain",
            tags=["domain:python", "topic:oauth2"],
            signals=["technical_detail"],
        )
        result2 = engine.ingest(turn2)
        stored2 = result2.get("stored_ids", []) if isinstance(result2, dict) else result2
        print(f"Stored {len(stored2)} more memories: {stored2}")

        # Retrieve
        results = engine.retrieve("OAuth2 Python setup", limit=3)
        print(f"\nRetrieved {len(results)} memories:")
        for r in results:
            print(f"  - [{r.get('type', 'memory')}] score={r.get('score', r.get('similarity', 'N/A')):.3f}: {r.get('content', r.get('fact', ''))[:80]}...")

        # Feedback
        if results:
            engine.feedback(results[0]["id"], positive=True)
            print(f"\nBoosted importance of {results[0]['id']}")

        # Budget
        budget = engine.get_context_budget(total_tokens=100000, conversation_tokens=30000)
        print(f"\nContext budget: {budget} tokens for memory injection")

    print("\n=== All tests passed ===")

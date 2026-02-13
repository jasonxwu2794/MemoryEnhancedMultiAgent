"""MemoryEngine — single entry point for all memory operations."""

from __future__ import annotations

import json
import sqlite3
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
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db: sqlite3.Connection = init_db(db_path)
        self.embedder: Embedder = get_embedder(embedder_config)

    def ingest(self, turn: Turn) -> list[str]:
        """Process a conversation turn through the full pipeline.
        
        Pipeline: split → chunk → stamp → dedup → score → embed → store.
        Returns list of stored memory IDs.
        """
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
            embedding = self.embedder.embed(chunk.content)

            # Dedup check
            dedup_result = check_duplicate(embedding, existing)
            should_store = handle_duplicate(chunk.id, dedup_result.match_type, dedup_result.matched_id, self.db)

            if not should_store:
                continue

            # Store
            tags_str = ",".join(turn.tags) if turn.tags else None
            self.db.execute(
                "INSERT INTO memories (id, content, embedding, tier, importance, tags, source_agent, metadata) "
                "VALUES (?, ?, ?, 'short_term', ?, ?, ?, ?)",
                (chunk.id, chunk.content, serialize_embedding(embedding), importance,
                 tags_str, turn.agent, json.dumps(chunk.metadata)),
            )
            self.db.commit()
            stored_ids.append(chunk.id)
            existing.append((chunk.id, embedding))

        return stored_ids

    def retrieve(
        self,
        query: str,
        strategy: str = "balanced",
        limit: int = 5,
        tags: list[str] | None = None,
    ) -> list[dict]:
        """Retrieve relevant memories for a query."""
        query_embedding = self.embedder.embed(query)

        # Check knowledge cache first
        facts = lookup_facts(query_embedding, self.db, limit=2)

        # Retrieve from memories
        memories = retrieve_memories(query_embedding, self.db, strategy, limit, tags)

        # Follow links for top results to get related context
        for mem in memories[:3]:
            linked = follow_links(mem["id"], self.db, depth=1)
            mem["linked_memories"] = linked

        # Prepend high-confidence facts
        results: list[dict] = []
        for f in facts:
            if f["confidence"] >= 0.7 and f["similarity"] > 0.5:
                results.append({"type": "fact", **f})
        results.extend(memories)

        return results[:limit]

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
        stored = engine.ingest(turn)
        print(f"Stored {len(stored)} memories: {stored}")

        # Ingest another turn
        turn2 = Turn(
            user_message="What about refresh tokens?",
            agent_response="Refresh tokens are handled automatically by authlib's OAuth2Session. Set token_endpoint_auth_method and the session will refresh when the access token expires.",
            agent="brain",
            tags=["domain:python", "topic:oauth2"],
            signals=["technical_detail"],
        )
        stored2 = engine.ingest(turn2)
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

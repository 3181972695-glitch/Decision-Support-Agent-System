"""Memory service — SQLite-backed persistent memory for user context.

Stores and retrieves decision memories, user preferences, and context
to provide continuity across conversations.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("app.services.memory_service")

DB_PATH = Path(__file__).resolve().parent.parent / "memory.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL DEFAULT 'demo_user',
    memory_type   TEXT NOT NULL DEFAULT 'decision',
    content       TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
"""


class MemoryService:
    """Persistent memory store for user decisions and preferences."""

    def __init__(self, db_path: str | Path = DB_PATH) -> None:
        self._db_path = str(db_path)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            conn.executescript(CREATE_TABLE_SQL)
            conn.commit()
            logger.info("[MEMORY] DB initialized at %s", self._db_path)
        except Exception as exc:
            logger.error("[MEMORY] DB init error: %s", exc)
            raise
        finally:
            conn.close()

    def save_memory(
        self,
        content: str,
        memory_type: str = "decision",
        user_id: str = "demo_user",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Store a memory entry. Returns the new memory ID."""
        conn = self._get_conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            meta_json = json.dumps(metadata or {}, ensure_ascii=False)
            cur = conn.execute(
                "INSERT INTO memories (user_id, memory_type, content, metadata_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, memory_type, content, meta_json, now),
            )
            conn.commit()
            mem_id = cur.lastrowid
            logger.info("[MEMORY] saved id=%d type=%s user=%s", mem_id, memory_type, user_id)
            return mem_id  # type: ignore[return-value]
        finally:
            conn.close()

    def retrieve_memory(
        self,
        query: str,
        user_id: str = "demo_user",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve memories relevant to the given query.

        Uses simple keyword-matching for relevance scoring.
        Returns sorted by relevance descending.
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT id, user_id, memory_type, content, metadata_json, created_at "
                "FROM memories WHERE user_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, limit * 3),
            ).fetchall()

            query_lower = query.lower()
            query_words = set(query_lower.split())

            scored: list[tuple[float, dict[str, Any]]] = []
            for row in rows:
                content_lower = (row["content"] or "").lower()
                meta = json.loads(row["metadata_json"] or "{}")
                meta_content = json.dumps(meta).lower() if meta else ""

                # Simple relevance scoring
                score = 0.0
                for word in query_words:
                    if len(word) <= 2:
                        continue
                    if word in content_lower:
                        score += 0.2
                    if word in meta_content:
                        score += 0.1

                # Boost recent memories
                age_hours = _age_hours(row["created_at"])
                if age_hours < 1:
                    score += 0.15
                elif age_hours < 24:
                    score += 0.1
                elif age_hours < 168:
                    score += 0.05

                # Boost decision-type memories
                if row["memory_type"] == "decision":
                    score += 0.1

                if score > 0:
                    scored.append((score, {
                        "id": row["id"],
                        "user_id": row["user_id"],
                        "memory_type": row["memory_type"],
                        "content": row["content"],
                        "metadata": meta,
                        "created_at": row["created_at"],
                        "relevance": round(min(score, 1.0), 2),
                    }))

            scored.sort(key=lambda x: -x[0])
            return [item[1] for item in scored[:limit]]
        finally:
            conn.close()

    def list_memories(
        self,
        user_id: str = "demo_user",
        memory_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List all memories for a user, optionally filtered by type."""
        conn = self._get_conn()
        try:
            if memory_type:
                rows = conn.execute(
                    "SELECT id, user_id, memory_type, content, metadata_json, created_at "
                    "FROM memories WHERE user_id = ? AND memory_type = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (user_id, memory_type, limit),
                )
            else:
                rows = conn.execute(
                    "SELECT id, user_id, memory_type, content, metadata_json, created_at "
                    "FROM memories WHERE user_id = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit),
                )
            results = []
            for row in rows:
                results.append({
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "memory_type": row["memory_type"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata_json"] or "{}"),
                    "created_at": row["created_at"],
                })
            return results
        finally:
            conn.close()

    def get_memory(self, memory_id: int) -> dict[str, Any] | None:
        """Get a single memory by ID."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT id, user_id, memory_type, content, metadata_json, created_at "
                "FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "id": row["id"],
                "user_id": row["user_id"],
                "memory_type": row["memory_type"],
                "content": row["content"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
                "created_at": row["created_at"],
            }
        finally:
            conn.close()

    def delete_memory(self, memory_id: int) -> bool:
        """Delete a memory by ID. Returns True if deleted."""
        conn = self._get_conn()
        try:
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            deleted = cur.rowcount > 0
            if deleted:
                logger.info("[MEMORY] deleted id=%d", memory_id)
            return deleted
        finally:
            conn.close()

    def delete_all_for_user(self, user_id: str = "demo_user") -> int:
        """Delete all memories for a user. Returns count deleted."""
        conn = self._get_conn()
        try:
            cur = conn.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
            conn.commit()
            deleted = cur.rowcount
            logger.info("[MEMORY] deleted %d memories for user=%s", deleted, user_id)
            return deleted
        finally:
            conn.close()

    def format_context(self, memories: list[dict[str, Any]]) -> str:
        """Format retrieved memories as context text for LLM prompts."""
        if not memories:
            return ""
        parts = ["Previous user context:"]
        for mem in memories:
            parts.append(f"- {mem['content']} (relevance: {mem.get('relevance', 0):.0%})")
        return "\n".join(parts)

    def store_decision(
        self,
        question: str,
        decision: str,
        confidence: int,
        mode: str,
    ) -> int:
        """Convenience: store a debate decision as a memory."""
        return self.save_memory(
            content=f"Decision: {decision[:200]}",
            memory_type="decision",
            metadata={
                "question": question[:200],
                "confidence": confidence,
                "mode": mode,
            },
        )

    def update_memory(self, memory_id: int, content: str, memory_type: str | None = None) -> bool:
        """Update a memory's content and optionally its type. Returns True if updated."""
        conn = self._get_conn()
        try:
            if memory_type:
                cur = conn.execute(
                    "UPDATE memories SET content = ?, memory_type = ? WHERE id = ?",
                    (content, memory_type, memory_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE memories SET content = ? WHERE id = ?",
                    (content, memory_id),
                )
            conn.commit()
            updated = cur.rowcount > 0
            if updated:
                logger.info("[MEMORY] updated id=%d", memory_id)
            return updated
        finally:
            conn.close()

    def close(self) -> None:
        """No-op for SQLite (connections are per-call). Included for interface compatibility."""
        pass


def _age_hours(iso_timestamp: str) -> float:
    """Calculate age of a timestamp in hours."""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).total_seconds() / 3600
    except Exception:
        return 999

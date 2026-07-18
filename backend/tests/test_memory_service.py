"""Tests for MemoryService."""

import time
from pathlib import Path

import pytest

from app.services.memory_service import MemoryService


@pytest.fixture
def memory(tmp_path: Path) -> MemoryService:
    """Create a MemoryService with a temp SQLite database."""
    db_path = tmp_path / "test_memory.db"
    return MemoryService(db_path=str(db_path))


@pytest.mark.asyncio
async def test_save_and_get_memory(memory: MemoryService) -> None:
    """Should save a memory and retrieve it by ID."""
    mem_id = memory.save_memory(
        content="User prefers gradual AI adoption",
        memory_type="preference",
        metadata={"source": "conversation"},
    )
    assert mem_id > 0

    retrieved = memory.get_memory(mem_id)
    assert retrieved is not None
    assert retrieved["content"] == "User prefers gradual AI adoption"
    assert retrieved["memory_type"] == "preference"
    assert retrieved["metadata"]["source"] == "conversation"


@pytest.mark.asyncio
async def test_list_memories(memory: MemoryService) -> None:
    """Should list all memories for a user."""
    memory.save_memory(content="First memory", memory_type="preference")
    memory.save_memory(content="Second memory", memory_type="decision")
    memories = memory.list_memories()
    assert len(memories) == 2


@pytest.mark.asyncio
async def test_list_memories_by_type(memory: MemoryService) -> None:
    """Should filter memories by type."""
    memory.save_memory(content="Pref 1", memory_type="preference")
    memory.save_memory(content="Dec 1", memory_type="decision")
    memory.save_memory(content="Ctx 1", memory_type="context")

    decisions = memory.list_memories(memory_type="decision")
    assert len(decisions) == 1
    assert decisions[0]["content"] == "Dec 1"


@pytest.mark.asyncio
async def test_delete_memory(memory: MemoryService) -> None:
    """Should delete a memory by ID."""
    mem_id = memory.save_memory(content="To delete", memory_type="decision")
    assert memory.get_memory(mem_id) is not None

    deleted = memory.delete_memory(mem_id)
    assert deleted is True
    assert memory.get_memory(mem_id) is None


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_false(memory: MemoryService) -> None:
    """Deleting a non-existent memory should return False."""
    assert memory.delete_memory(99999) is False


@pytest.mark.asyncio
async def test_delete_all_for_user(memory: MemoryService) -> None:
    """Should delete all memories for a user."""
    memory.save_memory(content="Mem 1", memory_type="decision")
    memory.save_memory(content="Mem 2", memory_type="preference")
    assert len(memory.list_memories()) == 2

    count = memory.delete_all_for_user()
    assert count == 2
    assert len(memory.list_memories()) == 0


@pytest.mark.asyncio
async def test_retrieve_memory_by_relevance(memory: MemoryService) -> None:
    """Should return relevant memories for a query."""
    memory.save_memory(
        content="User is a startup founder with limited budget",
        memory_type="context",
    )
    memory.save_memory(
        content="User prefers Python over Java for backend",
        memory_type="preference",
    )

    # Query about startup should return the first memory with higher relevance
    results = memory.retrieve_memory(query="startup budget", limit=5)
    assert len(results) > 0
    # At least one result should mention startup
    startup_results = [r for r in results if "startup" in r["content"].lower()]
    assert len(startup_results) > 0


@pytest.mark.asyncio
async def test_store_decision(memory: MemoryService) -> None:
    """store_decision should save a decision memory with metadata."""
    mem_id = memory.store_decision(
        question="Should we migrate?",
        decision="Gradual migration recommended",
        confidence=85,
        mode="software",
    )
    assert mem_id > 0
    retrieved = memory.get_memory(mem_id)
    assert retrieved is not None
    assert retrieved["memory_type"] == "decision"
    assert retrieved["metadata"]["question"] == "Should we migrate?"
    assert retrieved["metadata"]["confidence"] == 85


@pytest.mark.asyncio
async def test_format_context(memory: MemoryService) -> None:
    """format_context should produce formatted text."""
    memories = [
        {"content": "User is a startup", "relevance": 0.9},
        {"content": "User likes Python", "relevance": 0.5},
    ]
    context = memory.format_context(memories)
    assert "Previous user context:" in context
    assert "startup" in context
    assert "Python" in context


@pytest.mark.asyncio
async def test_format_context_empty(memory: MemoryService) -> None:
    """Empty memories list should return empty string."""
    assert memory.format_context([]) == ""


@pytest.mark.asyncio
async def test_new_memories_appear_first(memory: MemoryService) -> None:
    """Most recent memories should appear first in list."""
    id1 = memory.save_memory(content="Older memory", memory_type="preference")
    time.sleep(0.01)
    id2 = memory.save_memory(content="Newer memory", memory_type="preference")
    memories = memory.list_memories()
    assert memories[0]["id"] == id2
    assert memories[1]["id"] == id1

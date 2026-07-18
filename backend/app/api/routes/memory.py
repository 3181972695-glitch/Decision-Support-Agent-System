"""API routes for memory management."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.memory_service import MemoryService

logger = logging.getLogger("app.api.routes.memory")

router = APIRouter(prefix="/memory", tags=["memory"])


# ── Schemas ──────────────────────────────────────────────────────


class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    memory_type: str = Field(default="decision", pattern=r"^(decision|preference|context)$")
    user_id: str = Field(default="demo_user")
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryResponse(BaseModel):
    id: int
    user_id: str
    memory_type: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    relevance: float | None = None


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]
    total: int


# ── Dependency ────────────────────────────────────────────────────


def get_memory_service(request: Request) -> MemoryService:
    return request.app.state.memory_service  # type: ignore[no-any-return]


# ── Routes ────────────────────────────────────────────────────────


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    memory_type: str | None = None,
    limit: int = 50,
    service: MemoryService = Depends(get_memory_service),
):
    """List all memories for the demo user."""
    memories = service.list_memories(memory_type=memory_type, limit=limit)
    return {"memories": memories, "total": len(memories)}


@router.post("", response_model=MemoryResponse, status_code=201)
async def create_memory(
    payload: MemoryCreate,
    service: MemoryService = Depends(get_memory_service),
):
    """Create a new memory entry."""
    mem_id = service.save_memory(
        content=payload.content,
        memory_type=payload.memory_type,
        user_id=payload.user_id,
        metadata=payload.metadata,
    )
    mem = service.get_memory(mem_id)
    if mem is None:
        raise HTTPException(status_code=500, detail="Failed to create memory")
    return mem


@router.delete("/clear")
async def clear_all_memories(
    user_id: str = "demo_user",
    service: MemoryService = Depends(get_memory_service),
):
    """Delete all memories for a user."""
    count = service.delete_all_for_user(user_id)
    return {"deleted": count}


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: int,
    service: MemoryService = Depends(get_memory_service),
):
    """Delete a memory by ID."""
    deleted = service.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found")
    return {"deleted": True, "id": memory_id}

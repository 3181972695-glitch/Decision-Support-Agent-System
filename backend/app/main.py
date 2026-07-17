"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import agents so their @AgentRegistry.register decorators run.
# This must happen before any agent-dependent code executes.
import app.agents  # noqa: F401

from app.api.debates import router as debates_router
from app.api.routes.expert import router as expert_router
from app.api.sse import router as sse_router
from app.config import settings
from app.services.debate_service import DebateService
from app.services.expert_service import ExpertService
from app.services.llm_service import LLMService
from app.storage import create_repository as _create_repo

# ── Logging configuration ───────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize storage and services on startup."""
    repo = await _create_repo()
    llm_service = LLMService()
    app.state.debate_service = DebateService(
        repository=repo,
        llm_service=llm_service,
        agent_models=settings.AGENT_MODELS,
    )
    app.state.expert_service = ExpertService(llm_service=llm_service)
    yield


app = FastAPI(
    title="Decision Support Agent System",
    description="A multi-agent debate system for decision support.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(debates_router, prefix="/api")
app.include_router(sse_router, prefix="/api")
app.include_router(expert_router, prefix="/api")


@app.get("/health")
async def health_check():
    return {"status": "ok"}

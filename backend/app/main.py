"""FastAPI application entry point."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import agents so their @AgentRegistry.register decorators run.
# This must happen before any agent-dependent code executes.
import app.agents  # noqa: F401

from app.api.debates import router as debates_router
from app.config import settings

# ── Logging configuration ───────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(
    title="Decision Support Agent System",
    description="A multi-agent debate system for decision support.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(debates_router, prefix="/api")


@app.get("/health")
async def health_check():
    return {"status": "ok"}

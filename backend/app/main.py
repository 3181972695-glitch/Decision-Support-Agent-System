"""FastAPI application entry point."""

import logging
import logging.config
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

# Import agents so their @AgentRegistry.register decorators run.
# This must happen before any agent-dependent code executes.
import app.agents  # noqa: F401

from app.api.debates import router as debates_router
from app.api.routes.expert import router as expert_router
from app.api.routes.expert_debate import router as expert_debate_router
from app.api.routes.memory import router as memory_router
from app.api.sse import router as sse_router
from app.config import settings
from app.services.debate_service import DebateService
from app.services.expert_debate_service import ExpertDebateService
from app.services.expert_generator_service import ExpertGeneratorService
from app.services.expert_service import ExpertService
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.streaming_expert_service import StreamingExpertDebateService
from app.services.tool_service import ToolService
from app.storage import create_repository as _create_repo

# ── Structured logging ───────────────────────────────────────────
timestamper = structlog.processors.TimeStamper(fmt="iso")

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
# route standard library logs through structlog
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(message)s",
    force=True,
)
logging.getLogger().handlers.clear()
logging.getLogger().addHandler(logging.StreamHandler())
log = structlog.get_logger()

# ── Rate limiter ─────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/minute"],
    enabled=not settings.DEBUG,  # disabled in debug mode for dev convenience
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize storage and services on startup."""
    log.info("app.starting")
    repo = await _create_repo()
    llm_service = LLMService()
    expert_generator = ExpertGeneratorService(llm_service=llm_service)
    memory_service = MemoryService()
    tool_service = ToolService()

    app.state.debate_service = DebateService(
        repository=repo,
        llm_service=llm_service,
        agent_models=settings.AGENT_MODELS,
    )
    app.state.expert_service = ExpertService(llm_service=llm_service)
    app.state.memory_service = memory_service
    app.state.tool_service = tool_service
    app.state.expert_debate_service = ExpertDebateService(
        llm_service=llm_service, expert_generator=expert_generator,
        memory_service=memory_service, tool_service=tool_service,
    )
    app.state.streaming_expert_service = StreamingExpertDebateService(
        llm_service=llm_service, expert_generator=expert_generator,
        memory_service=memory_service, tool_service=tool_service,
    )
    log.info("app.started")
    yield
    log.info("app.stopping")


app = FastAPI(
    title="Decision Support Agent System",
    description="A multi-agent debate system for decision support.",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SlowAPIMiddleware)

app.include_router(debates_router, prefix="/api")
app.include_router(sse_router, prefix="/api")
app.include_router(expert_router, prefix="/api")
app.include_router(expert_debate_router, prefix="/api")
app.include_router(memory_router, prefix="/api")


@app.get("/health")
async def health_check():
    return {"status": "ok"}

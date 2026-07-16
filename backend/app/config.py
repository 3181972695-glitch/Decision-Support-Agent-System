"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Decision Support Agent System"
    DEBUG: bool = True

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # LLM Provider
    LLM_PROVIDER: str = "deepseek"
    LLM_BASE_URL: str = "http://localhost:4000/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "coder"
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.7

    # ── Per-role model routing ───────────────────────────────────
    MODERATOR_MODEL: str = ""
    ARGUMENT_MODEL: str = ""
    JUDGE_MODEL: str = ""

    # ── Per-role max_tokens ──────────────────────────────────────
    # Each agent role can have a different output token budget.
    # Falls back to LLM_MAX_TOKENS if zero.
    # DeepSeek V4 Pro uses thinking mode — needs extra token budget
    # for reasoning before producing visible content.
    MODERATOR_MAX_TOKENS: int = 2048
    OPENING_MAX_TOKENS: int = 3072
    REBUTTAL_MAX_TOKENS: int = 2048
    CROSS_EXAM_MAX_TOKENS: int = 2048
    JUDGE_MAX_TOKENS: int = 3072

    # ── Context window ───────────────────────────────────────────
    # Maximum characters of previous round context to include.
    # Keeps input tokens constant across rounds.
    CONTEXT_MAX_CHARS: int = 1500

    # Demo mode
    DEMO_MODE: bool = False
    DEMO_LLM_MAX_TOKENS: int = 4096

    # ── Legacy ───────────────────────────────────────────────────
    AGENT_MODELS: dict[str, str] = {}

    # Database
    DB_BACKEND: str = "memory"
    DATABASE_URL: str = "sqlite+aiosqlite:///debates.db"


settings = Settings()

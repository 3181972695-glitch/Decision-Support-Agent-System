"""Tests for application configuration loading via .env and environment variables."""

from __future__ import annotations

import os
from unittest.mock import patch


class TestSettingsEnvFile:
    """Verify that Settings loads values from a .env file."""

    def test_loads_llm_api_key_from_env_file(self) -> None:
        """LLM_API_KEY should be read from .env when present."""
        from app.config import Settings

        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=".env")  # type: ignore[call-arg]
            assert settings.LLM_API_KEY != "", (
                "Expected LLM_API_KEY to be loaded from .env, got empty string"
            )

    def test_loads_llm_base_url_from_env_file(self) -> None:
        """LLM_BASE_URL should be read from .env when present."""
        from app.config import Settings

        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=".env")  # type: ignore[call-arg]
            assert settings.LLM_BASE_URL == "https://api.deepseek.com/v1", (
                f"Expected LLM_BASE_URL from .env, got {settings.LLM_BASE_URL!r}"
            )

    def test_llm_base_url_from_env_var(self) -> None:
        """LLM_BASE_URL should be overridable via environment variable."""
        from app.config import Settings

        with patch.dict(os.environ, {"LLM_BASE_URL": "http://localhost:4000/v1"}, clear=True):
            settings = Settings()
            assert settings.LLM_BASE_URL == "http://localhost:4000/v1"

    def test_llm_api_key_from_env_var(self) -> None:
        """LLM_API_KEY should be overridable via environment variable."""
        from app.config import Settings

        with patch.dict(os.environ, {"LLM_API_KEY": "sk-test-env-key"}, clear=True):
            settings = Settings()
            assert settings.LLM_API_KEY == "sk-test-env-key"

    def test_default_llm_base_url_when_not_set(self) -> None:
        """LLM_BASE_URL should use the default when no .env or env var is set."""
        from app.config import Settings

        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            assert settings.LLM_BASE_URL == "http://localhost:4000/v1", (
                "Expected default LLM_BASE_URL to be http://localhost:4000/v1"
            )

    def test_default_llm_api_key_empty_when_not_set(self) -> None:
        """LLM_API_KEY should be empty string when no .env or env var is set."""
        from app.config import Settings

        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            assert settings.LLM_API_KEY == ""

    def test_demo_mode_default(self) -> None:
        """DEMO_MODE should default to False."""
        from app.config import Settings

        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            assert settings.DEMO_MODE is False

    def test_env_var_overrides_env_file(self) -> None:
        """Environment variables should take precedence over .env file values."""
        from app.config import Settings

        with patch.dict(
            os.environ,
            {"LLM_API_KEY": "sk-env-override"},
            clear=True,
        ):
            settings = Settings(_env_file=".env")  # type: ignore[call-arg]
            assert settings.LLM_API_KEY == "sk-env-override", (
                "Environment variable should override .env file value"
            )

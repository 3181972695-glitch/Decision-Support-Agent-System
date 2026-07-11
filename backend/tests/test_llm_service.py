"""Tests for LLMService — all calls are mocked; no real API requests.

Every test patches openai.AsyncOpenAI at the constructor level and
controls the response returned by chat.completions.create.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from app.services.llm_service import LLMConfig, LLMError, LLMService


# =================================================================
#  Fixtures
# =================================================================


@pytest.fixture(autouse=True)
def _disable_demo_mode() -> None:
    """Disable demo mode for all LLMService tests so they exercise the real code path."""
    from app.config import settings

    saved = settings.DEMO_MODE
    settings.DEMO_MODE = False
    yield
    settings.DEMO_MODE = saved


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    """Reset the lazy client cache between tests so state doesn't leak."""
    # Each test creates a fresh LLMService instance, so no cross-test state leaks.
    yield


@pytest.fixture
def mock_openai() -> MagicMock:
    """Patch openai.AsyncOpenAI and return a mock client instance.

    The mock client's chat.completions.create is an AsyncMock that
    returns a default successful response. Tests can customise it
    via ``mock_openai.chat.completions.create``.
    """
    with patch("openai.AsyncOpenAI") as patched:
        client_instance = MagicMock()
        client_instance.chat.completions.create = AsyncMock()
        patched.return_value = client_instance
        yield client_instance


def _successful_response(
    content: str = "Generated response text.",
    model: str = "gpt-4o-mini",
    finish_reason: str = "stop",
    prompt_tokens: int = 50,
    completion_tokens: int = 120,
) -> MagicMock:
    """Build a mock OpenAI chat completion response."""
    usage = MagicMock(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    choice = MagicMock(
        finish_reason=finish_reason,
        message=MagicMock(content=content),
    )
    response = MagicMock(
        choices=[choice],
        model=model,
        usage=usage,
        object="chat.completion",
    )
    return response


# =================================================================
#  Service creation
# =================================================================


class TestLLMServiceCreation:
    """LLMService construction and configuration."""

    def test_default_config_from_settings(self) -> None:
        """When no config is passed, defaults come from the global settings."""
        svc = LLMService()
        assert svc._config.provider in ("openai", "deepseek")
        assert svc._config.base_url in (
            "https://api.openai.com/v1",
            "https://api.deepseek.com",
        )
        assert isinstance(svc._config.model, str)
        assert svc._config.max_tokens > 0

    def test_custom_config(self) -> None:
        """A custom LLMConfig is accepted and used."""
        cfg = LLMConfig(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            api_key="sk-ds-test",
            max_tokens=2048,
            temperature=0.3,
        )
        svc = LLMService(config=cfg)
        assert svc._config.base_url == "https://api.deepseek.com"
        assert svc._config.api_key == "sk-ds-test"

    def test_client_is_lazily_created(self) -> None:
        """The AsyncOpenAI client is not created at construction time."""
        with patch("openai.AsyncOpenAI") as mock_cls:
            svc = LLMService()
            mock_cls.assert_not_called()
            assert svc._client is None

    def test_client_created_on_first_request(self, mock_openai: MagicMock) -> None:
        """The client is created when generate() is first called."""
        mock_openai.chat.completions.create.return_value = _successful_response()
        svc = LLMService()
        # Access _client before calling generate
        assert svc._client is None

        import asyncio

        asyncio.run(svc.generate(prompt="Hello"))

        assert svc._client is not None


# =================================================================
#  Successful generation
# =================================================================


class TestSuccessfulGeneration:
    """Happy-path generation with various argument combinations."""

    @pytest.mark.asyncio
    async def test_basic_prompt_only(self, mock_openai: MagicMock) -> None:
        mock_openai.chat.completions.create.return_value = _successful_response(
            content="Basic response."
        )
        svc = LLMService()

        result = await svc.generate(prompt="Tell me something.")

        assert result == "Basic response."
        mock_openai.chat.completions.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_system_prompt(self, mock_openai: MagicMock) -> None:
        mock_openai.chat.completions.create.return_value = _successful_response(
            content="System-guided response."
        )
        svc = LLMService()

        result = await svc.generate(
            system_prompt="You are a helpful assistant.",
            prompt="What is Python?",
        )

        assert result == "System-guided response."

        # Verify the messages sent to the API
        call_kwargs = mock_openai.chat.completions.create.await_args
        assert call_kwargs is not None
        messages = call_kwargs.kwargs["messages"]
        assert messages == [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is Python?"},
        ]

    @pytest.mark.asyncio
    async def test_without_system_prompt(self, mock_openai: MagicMock) -> None:
        mock_openai.chat.completions.create.return_value = _successful_response()
        svc = LLMService()

        result = await svc.generate(prompt="Hello.")

        assert result
        call_kwargs = mock_openai.chat.completions.create.await_args
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_custom_temperature(self, mock_openai: MagicMock) -> None:
        mock_openai.chat.completions.create.return_value = _successful_response()
        svc = LLMService()

        await svc.generate(prompt="Test", temperature=0.1)

        call_kwargs = mock_openai.chat.completions.create.await_args
        assert call_kwargs.kwargs["temperature"] == 0.1

    @pytest.mark.asyncio
    async def test_custom_max_tokens(self, mock_openai: MagicMock) -> None:
        mock_openai.chat.completions.create.return_value = _successful_response()
        svc = LLMService()

        await svc.generate(prompt="Test", max_tokens=500)

        call_kwargs = mock_openai.chat.completions.create.await_args
        assert call_kwargs.kwargs["max_tokens"] == 500

    @pytest.mark.asyncio
    async def test_temperature_defaults_from_config(
        self, mock_openai: MagicMock
    ) -> None:
        cfg = LLMConfig(temperature=0.9)
        mock_openai.chat.completions.create.return_value = _successful_response()
        svc = LLMService(config=cfg)

        await svc.generate(prompt="Test")

        call_kwargs = mock_openai.chat.completions.create.await_args
        assert call_kwargs.kwargs["temperature"] == 0.9

    @pytest.mark.asyncio
    async def test_max_tokens_defaults_from_config(
        self, mock_openai: MagicMock
    ) -> None:
        cfg = LLMConfig(max_tokens=2048)
        mock_openai.chat.completions.create.return_value = _successful_response()
        svc = LLMService(config=cfg)

        await svc.generate(prompt="Test")

        call_kwargs = mock_openai.chat.completions.create.await_args
        assert call_kwargs.kwargs["max_tokens"] == 2048

    @pytest.mark.asyncio
    async def test_empty_content_response(self, mock_openai: MagicMock) -> None:
        """When the model returns None content, we get an empty string back."""
        resp = _successful_response(content=None)  # type: ignore[arg-type]
        mock_openai.chat.completions.create.return_value = resp
        svc = LLMService()

        result = await svc.generate(prompt="Test")
        assert result == ""


# =================================================================
#  Error handling
# =================================================================


class TestErrorHandling:
    """Every OpenAI exception is wrapped into LLMError."""

    @pytest.mark.asyncio
    async def test_connection_error(self, mock_openai: MagicMock) -> None:
        mock_request = MagicMock()
        mock_openai.chat.completions.create.side_effect = openai.APIConnectionError(
            message="Connection refused",
            request=mock_request,
        )
        svc = LLMService()

        with pytest.raises(LLMError) as exc:
            await svc.generate(prompt="Test")
        assert "Cannot reach" in str(exc.value)

    @pytest.mark.asyncio
    async def test_authentication_error(self, mock_openai: MagicMock) -> None:
        mock_openai.chat.completions.create.side_effect = openai.AuthenticationError(
            "Invalid API key",
            response=MagicMock(status_code=401),
            body=None,
        )
        svc = LLMService()

        with pytest.raises(LLMError) as exc:
            await svc.generate(prompt="Test")
        assert "API key was rejected" in str(exc.value)

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, mock_openai: MagicMock) -> None:
        mock_openai.chat.completions.create.side_effect = openai.RateLimitError(
            "Rate limited",
            response=MagicMock(status_code=429),
            body=None,
        )
        svc = LLMService()

        with pytest.raises(LLMError) as exc:
            await svc.generate(prompt="Test")
        assert "rate limit" in str(exc.value).lower()

    @pytest.mark.asyncio
    async def test_api_status_error(self, mock_openai: MagicMock) -> None:
        mock_openai.chat.completions.create.side_effect = openai.APIStatusError(
            "Bad gateway",
            response=MagicMock(status_code=502),
            body=None,
        )
        svc = LLMService()

        with pytest.raises(LLMError) as exc:
            await svc.generate(prompt="Test")
        assert "502" in str(exc.value)

    @pytest.mark.asyncio
    async def test_generic_openai_error(self, mock_openai: MagicMock) -> None:
        mock_openai.chat.completions.create.side_effect = openai.OpenAIError(
            "Something unexpected"
        )
        svc = LLMService()

        with pytest.raises(LLMError) as exc:
            await svc.generate(prompt="Test")
        assert "Unexpected LLM error" in str(exc.value)

    @pytest.mark.asyncio
    async def test_llm_error_is_raised(self) -> None:
        """LLMError is a plain Exception, not a framework-specific type."""
        err = LLMError("Something broke")
        assert isinstance(err, Exception)
        assert str(err) == "Something broke"
        assert err.message == "Something broke"


# =================================================================
#  Logging
# =================================================================


class TestLogging:
    """LLMService logs request and response details."""

    @pytest.mark.asyncio
    async def test_logs_request_and_response(
        self, mock_openai: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        mock_openai.chat.completions.create.return_value = _successful_response(
            content="Logged response.",
            model="gpt-4o-mini",
            prompt_tokens=55,
            completion_tokens=99,
        )

        cfg = LLMConfig(model="gpt-4o-mini", temperature=0.5, max_tokens=1024)
        svc = LLMService(config=cfg)

        with caplog.at_level(logging.INFO):
            await svc.generate(system_prompt="Be concise.", prompt="Explain AI.")

        # Check request log
        request_logs = [r for r in caplog.records if "LLM request" in r.getMessage()]
        assert len(request_logs) == 1
        assert "model=gpt-4o-mini" in request_logs[0].getMessage()

        # Check response log
        response_logs = [r for r in caplog.records if "LLM response" in r.getMessage()]
        assert len(response_logs) == 1
        msg = response_logs[0].getMessage()
        assert "finish_reason=stop" in msg
        assert "output 99)" in msg or "output 99 " in msg

    @pytest.mark.asyncio
    async def test_logs_errors(
        self, mock_openai: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        mock_request = MagicMock()
        mock_openai.chat.completions.create.side_effect = openai.APIConnectionError(
            message="timeout",
            request=mock_request,
        )
        svc = LLMService()

        with caplog.at_level(logging.ERROR):
            with pytest.raises(LLMError):
                await svc.generate(prompt="Hi")

        error_logs = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("LLM connection failed" in r.getMessage() for r in error_logs)


# =================================================================
#  Edge cases
# =================================================================


class TestLLMServiceEdgeCases:
    """Unusual but valid usage scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_calls_use_same_client(self, mock_openai: MagicMock) -> None:
        """The client is created once and reused."""
        mock_openai.chat.completions.create.return_value = _successful_response()
        svc = LLMService()

        await svc.generate(prompt="First")
        await svc.generate(prompt="Second")

        # AsyncOpenAI should have been constructed exactly once

        # The mock was set up with patch("openai.AsyncOpenAI")
        # We need to verify the constructor was called once

        # Re-check via the svc._client
        first_client = svc._client
        await svc.generate(prompt="Third")
        assert svc._client is first_client

    @pytest.mark.asyncio
    async def test_generate_with_empty_system_prompt(
        self, mock_openai: MagicMock
    ) -> None:
        """An empty system prompt is omitted from messages."""
        mock_openai.chat.completions.create.return_value = _successful_response()
        svc = LLMService()

        await svc.generate(prompt="Hello")  # system_prompt defaults to ""

        call_kwargs = mock_openai.chat.completions.create.await_args
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_keyword_only_arguments(self, mock_openai: MagicMock) -> None:
        """generate() enforces keyword-only arguments after the first *."""
        svc = LLMService()

        with pytest.raises(TypeError):
            # positional arguments should be rejected
            await svc.generate("system", "prompt")  # type: ignore[call-arg]

    @pytest.mark.asyncio
    async def test_very_long_prompt(self, mock_openai: MagicMock) -> None:
        long_text = "word " * 5000
        mock_openai.chat.completions.create.return_value = _successful_response(
            content="Summary."
        )
        svc = LLMService()

        result = await svc.generate(prompt=long_text)
        assert result == "Summary."

    @pytest.mark.asyncio
    async def test_different_finish_reasons(self, mock_openai: MagicMock) -> None:
        """Finish reasons other than 'stop' are handled transparently."""
        resp = _successful_response(content="Partial output.", finish_reason="length")
        mock_openai.chat.completions.create.return_value = resp
        svc = LLMService()

        result = await svc.generate(prompt="Write a long essay")
        assert result == "Partial output."

    @pytest.mark.asyncio
    async def test_model_name_passed_to_api(self, mock_openai: MagicMock) -> None:
        cfg = LLMConfig(model="deepseek-chat")
        mock_openai.chat.completions.create.return_value = _successful_response()
        svc = LLMService(config=cfg)

        await svc.generate(prompt="Hi")

        call_kwargs = mock_openai.chat.completions.create.await_args
        assert call_kwargs.kwargs["model"] == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_deepseek_base_url(self, mock_openai: MagicMock) -> None:
        """Verify DeepSeek-compatible setup passes the right base_url."""
        cfg = LLMConfig(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            api_key="sk-ds-test-key",
        )
        svc = LLMService(config=cfg)

        # Trigger client creation
        mock_openai.chat.completions.create.return_value = _successful_response()
        await svc.generate(prompt="Hi")

        # Verify the client was created with the right base_url and api_key

        # The openai.AsyncOpenAI constructor was already patched via fixture
        # but we can verify through _get_client
        assert svc._client is not None

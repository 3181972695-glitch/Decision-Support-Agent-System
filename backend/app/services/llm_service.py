"""Provider-independent abstraction over LLM API calls.

Uses the OpenAI Python SDK under the hood but accepts any
OpenAI-compatible endpoint (OpenAI, DeepSeek, etc.) via base_url.
All configuration is read from app.config.settings.

Supports a DEMO_MODE that returns simulated responses so the full
debate flow can be demonstrated without a live LLM API key.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import openai

from app.config import settings
from app.prompts.base import extract_topic, extract_response_type, extract_round_focus, extract_round, extract_stance

logger = logging.getLogger("app.services.llm_service")


# ── Profiler ────────────────────────────────────────────────────


@dataclass
class LLMCallProfile:
    """A single LLM call performance record."""
    role: str = ""
    model: str = ""
    start_time: float = 0.0
    first_token_time: float = 0.0
    end_time: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    retry_count: int = 0
    streamed: bool = False
    error: str | None = None

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def ttft(self) -> float:
        """Time to first token."""
        if self.first_token_time > 0:
            return self.first_token_time - self.start_time
        return self.duration

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "model": self.model,
            "duration": round(self.duration, 3),
            "ttft": round(self.ttft, 3),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "retry_count": self.retry_count,
            "streamed": self.streamed,
            "error": self.error,
        }


class LLMProfiler:
    """Collects per-call profiles for a debate session."""

    def __init__(self) -> None:
        self.calls: list[LLMCallProfile] = []

    def start_call(self, role: str, model: str, streamed: bool) -> LLMCallProfile:
        profile = LLMCallProfile(
            role=role,
            model=model,
            start_time=time.perf_counter(),
            streamed=streamed,
        )
        self.calls.append(profile)
        return profile

    @property
    def total_calls(self) -> int:
        return len(self.calls)

    @property
    def total_duration(self) -> float:
        return sum(c.duration for c in self.calls)

    @property
    def average_latency(self) -> float:
        if not self.calls:
            return 0.0
        return self.total_duration / len(self.calls)

    @property
    def slowest_call(self) -> LLMCallProfile | None:
        if not self.calls:
            return None
        return max(self.calls, key=lambda c: c.duration)

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    @property
    def total_reasoning_tokens(self) -> int:
        return sum(c.reasoning_tokens for c in self.calls)

    def summary(self) -> dict[str, Any]:
        slowest = self.slowest_call
        return {
            "total_llm_calls": self.total_calls,
            "total_duration_s": round(self.total_duration, 3),
            "average_latency_s": round(self.average_latency, 3),
            "slowest_call_s": round(slowest.duration, 3) if slowest else 0.0,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_reasoning_tokens": self.total_reasoning_tokens,
            "estimated_cost": self._estimated_cost(),
            "calls": [c.to_dict() for c in self.calls],
        }

    def _estimated_cost(self) -> str:
        """Rough cost estimate based on common pricing tiers."""
        # Generic estimation: ~$2.00/M input, ~$8.00/M output, reasoning ~$55/M
        input_cost = self.total_input_tokens / 1_000_000 * 2.0
        output_cost = self.total_output_tokens / 1_000_000 * 8.0
        reasoning_cost = self.total_reasoning_tokens / 1_000_000 * 55.0
        total = input_cost + output_cost + reasoning_cost
        if total < 0.01:
            return "< $0.01"
        return f"${total:.2f}"


# ── Config ──────────────────────────────────────────────────────


@dataclass
class LLMConfig:
    """Configuration values used by LLMService."""

    provider: str = settings.LLM_PROVIDER
    base_url: str = settings.LLM_BASE_URL
    api_key: str = settings.LLM_API_KEY
    model: str = settings.LLM_MODEL
    max_tokens: int = settings.LLM_MAX_TOKENS
    temperature: float = settings.LLM_TEMPERATURE


MAX_RETRIES = 1
RETRY_DELAY_SECONDS = 1.5
DEFAULT_TIMEOUT = 120.0  # seconds per LLM call

# Content-level retry (empty/whitespace responses)
CONTENT_RETRY_MAX = 3
CONTENT_RETRY_BASE_DELAY = 1.0  # seconds, multiplied by attempt number


def _is_retryable(exc: openai.OpenAIError) -> bool:
    if isinstance(exc, (openai.APIConnectionError, openai.RateLimitError, openai.APITimeoutError, openai.InternalServerError)):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code >= 500
    return False


# ── Service ─────────────────────────────────────────────────────


def _is_valid_response(text: str | None) -> bool:
    if text is None:
        return False
    if not isinstance(text, str):
        return False
    return bool(text.strip())


_FALLBACK_TEXTS: dict[str, str] = {
    "opening": "Unable to generate an opening statement due to a temporary model failure. Please try again.",
    "rebuttal": "No rebuttal was generated because the language model returned an empty response.",
    "cross_examine_ask": "No question could be generated. Please proceed to the next stage.",
    "cross_examine_answer": "No answer could be generated. The model was unable to produce a response.",
    "moderator_intro": "The moderator was unable to introduce this round. Please proceed with the debate.",
    "moderator_summary": "No summary was generated because the language model returned an empty response.",
    "judge": "The judge could not generate a decision because the language model failed repeatedly. Please review the debate arguments manually.",
    "user_answer": "I was unable to generate a response to your question. Please try again.",
    "default": "No response was generated due to a temporary model failure.",
}


def _fallback_text(response_type: str | None = None) -> str:
    if response_type and response_type in _FALLBACK_TEXTS:
        return _FALLBACK_TEXTS[response_type]
    return _FALLBACK_TEXTS["default"]


class LLMService:
    """Wraps an OpenAI-compatible LLM API behind a simple interface."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self._config = config or LLMConfig()
        self._client: openai.AsyncOpenAI | None = None
        self._profiler: LLMProfiler | None = None
        self._timeout: float = DEFAULT_TIMEOUT

    def start_profiler(self) -> LLMProfiler:
        """Begin a new profiling session. Returns the profiler instance."""
        self._profiler = LLMProfiler()
        return self._profiler

    def get_profiler(self) -> LLMProfiler | None:
        return self._profiler

    # ── Public API ──────────────────────────────────────────────

    async def generate(
        self,
        *,
        system_prompt: str = "",
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
        response_format: dict[str, str] | None = None,
        role: str = "",
        timeout: float | None = None,
    ) -> str:
        effective_model = model if model is not None else self._config.model
        profile = self._start_profile(role, effective_model, streamed=False)

        if settings.DEMO_MODE:
            result = self._demo_response(system_prompt, prompt)
            self._finish_profile(profile)
            self._log_profile(profile)
            return result

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, object] = {
            "model": effective_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self._config.max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        prompt_len = len(prompt)
        logger.info(
            "[LLM_PROMPT] method=generate role=%s model=%s prompt_len=%d system_len=%d max_tokens=%s",
            role, effective_model, prompt_len, len(system_prompt),
            max_tokens if max_tokens is not None else self._config.max_tokens,
        )

        response_type = extract_response_type(prompt)

        content = await self._content_retry(
            role=role,
            effective_model=effective_model,
            messages=messages,
            kwargs=kwargs,
            profile=profile,
            response_type=response_type,
        )
        self._finish_profile(profile)
        self._log_profile(profile)
        return content

    async def generate_stream(
        self,
        *,
        system_prompt: str = "",
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
        response_format: dict[str, str] | None = None,
        role: str = "",
        timeout: float | None = None,
    ) -> AsyncGenerator[str, None]:
        effective_model = model if model is not None else self._config.model
        profile = self._start_profile(role, effective_model, streamed=True)

        if settings.DEMO_MODE:
            full = self._demo_response(system_prompt, prompt)
            words = full.split()
            chunk_size = max(1, len(words) // 15)
            for i in range(0, len(words), chunk_size):
                yield " ".join(words[i : i + chunk_size]) + " "
            self._finish_profile(profile)
            self._log_profile(profile)
            return

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, object] = {
            "model": effective_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self._config.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        prompt_len = len(prompt)
        logger.info(
            "[LLM_PROMPT] method=stream role=%s model=%s prompt_len=%d system_len=%d max_tokens=%s",
            role, effective_model, prompt_len, len(system_prompt),
            max_tokens if max_tokens is not None else self._config.max_tokens,
        )

        response_type = extract_response_type(prompt)
        collected: list[str] = []
        try:
            client = self._get_client()
            logger.debug("[STREAM_START] llm role=%s model=%s", role, effective_model)
            async with asyncio.timeout(timeout or self._timeout):
                stream = await self._retry(
                    lambda: client.chat.completions.create(**kwargs),
                    profile,
                )

            first_token = True
            chunk_count = 0
            async for chunk in stream:
                if first_token:
                    profile.first_token_time = time.perf_counter()
                    first_token = False
                    logger.debug(
                        "[STREAM_CHUNK] llm role=%s ttft=%.3fs",
                        role, profile.first_token_time - profile.start_time,
                    )

                chunk_count += 1
                if chunk.usage:
                    profile.input_tokens = chunk.usage.prompt_tokens or 0
                    profile.output_tokens = chunk.usage.completion_tokens or 0

                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    collected.append(delta.content)
                    yield delta.content

            self._finish_profile(profile)
            self._log_profile(profile)
            logger.debug(
                "[STREAM_END] llm role=%s chunks=%d duration=%.3fs",
                role, chunk_count, profile.duration,
            )

            # Validate assembled content. If empty, fall back to non-streaming
            # generate() with content-level retry and yield the result.
            assembled = "".join(collected)
            if chunk_count == 0 or not _is_valid_response(assembled):
                logger.warning(
                    "[LLM] Stream empty/invalid role=%s model=%s chunks=%d chars=%d -> falling back to retry",
                    role, effective_model, chunk_count, len(assembled),
                )
                profile2 = self._start_profile(role, effective_model, streamed=False)
                no_stream_kwargs = dict(kwargs)
                no_stream_kwargs.pop("stream", None)
                no_stream_kwargs.pop("stream_options", None)
                fallback_content = await self._content_retry(
                    role=role,
                    effective_model=effective_model,
                    messages=messages,
                    kwargs=no_stream_kwargs,
                    profile=profile2,
                    response_type=response_type,
                )
                self._finish_profile(profile2)
                self._log_profile(profile2)
                yield fallback_content

        except asyncio.TimeoutError:
            profile.error = f"timeout after {timeout or self._timeout}s"
            self._finish_profile(profile)
            self._log_profile(profile)
            raise LLMError(f"LLM stream timed out after {timeout or self._timeout}s") from None

        except openai.OpenAIError as exc:
            profile.error = str(exc)[:200]
            self._finish_profile(profile)
            self._log_profile(profile)
            raise self._wrap_llm_error(exc) from exc

    # ── Profiler helpers ───────────────────────────────────────

    def _start_profile(self, role: str, model: str, streamed: bool) -> LLMCallProfile:
        if self._profiler is None:
            self._profiler = LLMProfiler()
        return self._profiler.start_call(role, model, streamed)

    def _finish_profile(self, profile: LLMCallProfile) -> None:
        profile.end_time = time.perf_counter()

    async def _content_retry(
        self,
        role: str,
        effective_model: str,
        messages: list[dict[str, str]],
        kwargs: dict[str, object],
        profile: LLMCallProfile,
        response_type: str | None = None,
    ) -> str:
        last_content = ""
        for attempt in range(1, CONTENT_RETRY_MAX + 1):
            try:
                client = self._get_client()
                async with asyncio.timeout(self._timeout):
                    response = await self._retry(
                        lambda: client.chat.completions.create(**kwargs),
                        profile,
                    )
                choice = response.choices[0]
                content = choice.message.content or ""
                if response.usage:
                    profile.input_tokens = response.usage.prompt_tokens or 0
                    profile.output_tokens = response.usage.completion_tokens or 0
                    profile.reasoning_tokens = getattr(
                        response.usage, "completion_tokens_details", None
                    )
                    if profile.reasoning_tokens and hasattr(profile.reasoning_tokens, "reasoning_tokens"):
                        profile.reasoning_tokens = profile.reasoning_tokens.reasoning_tokens
                    else:
                        profile.reasoning_tokens = 0
                if _is_valid_response(content):
                    return content
                last_content = content
                logger.warning(
                    "[LLM] Empty response role=%s model=%s attempt=%d/%d response_type=%s chars=%d",
                    role, effective_model, attempt, CONTENT_RETRY_MAX,
                    response_type or "unknown", len(content) if content else 0,
                )
                if attempt < CONTENT_RETRY_MAX:
                    delay = CONTENT_RETRY_BASE_DELAY * attempt
                    logger.info("[LLM] Retrying in %.1fs...", delay)
                    await asyncio.sleep(delay)
            except asyncio.TimeoutError:
                profile.error = f"timeout after {self._timeout}s"
                logger.warning(
                    "[LLM] Timeout role=%s model=%s attempt=%d/%d",
                    role, effective_model, attempt, CONTENT_RETRY_MAX,
                )
                if attempt < CONTENT_RETRY_MAX:
                    await asyncio.sleep(CONTENT_RETRY_BASE_DELAY * attempt)
                else:
                    raise LLMError(f"LLM call timed out after {self._timeout}s") from None
            except openai.OpenAIError as exc:
                profile.error = str(exc)[:200]
                logger.warning(
                    "[LLM] API error role=%s model=%s attempt=%d/%d: %s",
                    role, effective_model, attempt, CONTENT_RETRY_MAX, exc,
                )
                if attempt < CONTENT_RETRY_MAX and _is_retryable(exc):
                    await asyncio.sleep(CONTENT_RETRY_BASE_DELAY * attempt)
                else:
                    raise self._wrap_llm_error(exc) from exc
        fallback = _fallback_text(response_type)
        logger.error(
            "[LLM] All retries exhausted role=%s model=%s attempts=%d response_type=%s -> returning fallback",
            role, effective_model, CONTENT_RETRY_MAX, response_type or "unknown",
        )
        return fallback

    def _log_profile(self, profile: LLMCallProfile) -> None:
        logger.info(
            "[LLM_PROFILE] role=%s model=%s duration=%.2fs ttft=%.2fs "
            "input=%d output=%d reasoning=%d retry=%d streamed=%s%s",
            profile.role,
            profile.model,
            profile.duration,
            profile.ttft,
            profile.input_tokens,
            profile.output_tokens,
            profile.reasoning_tokens,
            profile.retry_count,
            profile.streamed,
            f" error={profile.error}" if profile.error else "",
        )

    # ── Demo mode ───────────────────────────────────────────────

    def _demo_response(self, system_prompt: str, prompt: str) -> str:
        sys_lower = system_prompt.lower()
        if "moderator" in sys_lower:
            return self._demo_moderator(prompt)
        if "judge" in sys_lower or "verdict" in sys_lower or "impartial" in sys_lower:
            return self._demo_judge(prompt)
        if "against" in sys_lower or "challenger" in sys_lower or "opposition" in sys_lower:
            return self._demo_con(prompt)
        if "advocate" in sys_lower or "for" in sys_lower:
            return self._demo_pro(prompt)
        return (
            "A balanced assessment of the topic reveals several key considerations. "
            "On one hand, there are compelling reasons to pursue this path. "
            "On the other, important risks and trade-offs must be carefully weighed. "
            "Ultimately, the decision depends on your specific circumstances and priorities."
        )

    def _demo_pro(self, prompt: str) -> str:
        topic = extract_topic(prompt)
        stance = extract_stance(prompt)
        round_num = extract_round(prompt)
        response_type = extract_response_type(prompt)

        # For binary-choice debates, use the stance as the concrete position
        subject = stance if stance else topic

        if response_type == "rebuttal":
            if stance:
                return (
                    f"Let me defend {stance} against those criticisms. "
                    f"The concerns raised about {stance} are valid but overstated. "
                    f"The strengths of {stance} far outweigh any drawbacks, "
                    f"and the alternatives have their own issues.\n\n"
                    f"In fact, {stance} offers clear advantages that the opposition hasn't addressed. "
                    f"The practical benefits are well-documented and immediately verifiable."
                )
            return (
                f"Let me address the concerns raised. "
                f"The upfront investment is real, "
                f"but the long-term return consistently outstrips the initial outlay within two to three years. "
                f"The question is not whether other good options exist, but whether this path offers unique "
                f"advantages that alternatives do not. It clearly does.\n\n"
                f"On timing: the conditions align favourably right now. "
                f"Waiting often means higher barriers later. The smart approach is to start small, "
                f"validate early, and scale gradually."
            )
        if response_type == "cross_examine_ask":
            side = f" for choosing {stance}" if stance else ""
            return (
                f"A question for the opposition regarding {topic}: "
                f"Your argument assumes that current conditions will remain unchanged, "
                f"but what evidence do you have that these conditions will persist "
                f"given how rapidly circumstances are evolving?"
            )
        if response_type == "cross_examine_answer":
            return (
                f"To answer that question{'' if not stance else f' about {stance}'}: "
                f"That concern is valid in theory, but in practice the data shows "
                f"that the most successful approaches account for changing conditions "
                f"through regular reassessment and course correction. "
                f"The flexibility built into this approach is precisely one of its strengths."
            )
        if response_type == "user_answer":
            return (
                f"Thank you for the question about {topic}. "
                f"From my perspective supporting {subject}, "
                f"the evidence consistently favours this choice. "
                f"The key consideration is not whether to choose, but which factors matter most."
            )
        rounds = [
            (
                f"Let me make the case for {subject}.\n\n"
                f"First, {subject} offers clear and measurable advantages. "
                f"The evidence consistently shows that choosing {subject} leads to better outcomes "
                f"in both the short and long term.\n\n"
                f"Second, the practical benefits are substantial and well-documented. "
                f"Those who choose {subject} consistently report positive results "
                f"that justify the decision.\n\n"
                f"Third, the alternatives simply cannot match what {subject} provides. "
                f"The choice is clear when you look at the full picture."
            ),
            (
                f"The case for {subject} remains compelling. "
                f"The counterarguments raised have some merit in edge cases, "
                f"but they don't change the fundamental assessment.\n\n"
                f"The advantages of {subject} are real and demonstrable. "
                f"A thoughtful evaluation consistently favours this option."
            ),
            (
                f"As this discussion concludes, the argument for {subject} "
                f"stands on solid ground. The evidence has been consistent, "
                f"and the counterarguments, while noted, do not outweigh "
                f"the demonstrated benefits of {subject}."
            ),
        ]
        return rounds[min(round_num - 1, len(rounds) - 1)]

    def _demo_con(self, prompt: str) -> str:
        topic = extract_topic(prompt)
        stance = extract_stance(prompt)
        round_num = extract_round(prompt)
        response_type = extract_response_type(prompt)

        subject = stance if stance else topic

        if response_type == "rebuttal":
            if stance:
                return (
                    f"Let me defend {stance} against the proponent's claims. "
                    f"The arguments for the other option sound reasonable, "
                    f"but they overlook the real advantages that {stance} provides.\n\n"
                    f"The case for {stance} is strong when you consider the practical realities. "
                    f"It offers benefits that are often underestimated by its supporters."
                )
            return (
                f"Let me respond to the proponent's case. "
                f"The claimed advantages are overstated and highly dependent "
                f"on circumstances that may not apply to you. Personal growth can be achieved through "
                f"many less risky and less expensive means. This is not the only path to development.\n\n"
                f"As for timing, rushing into decisions often leads to regret. "
                f"A more measured approach allows for better information gathering. Consider starting "
                f"with a small-scale experiment before committing fully."
            )
        if response_type == "cross_examine_ask":
            return (
                f"A question for the proponent regarding {topic}: "
                f"You highlight the potential benefits, but can you provide concrete evidence "
                f"that these outcomes are typical rather than exceptional, "
                f"given the well-known survivorship bias in success stories?"
            )
        if response_type == "cross_examine_answer":
            return (
                f"To answer that question about {topic}: "
                f"While the proponent makes a reasonable point about potential upsides, "
                f"the key issue is that the risks are not evenly distributed. "
                f"Those who are not in an optimal position face disproportionately higher "
                f"downside that is often minimised in optimistic projections."
            )
        if response_type == "user_answer":
            return (
                f"Thank you for the question about {topic}. "
                f"From my perspective, the risks and opportunity costs are substantial. "
                f"A more measured, exploratory approach before any major commitment "
                f"is the prudent course of action."
            )
        rounds = [
            (
                f"Let me explain why {subject} is the better choice.\n\n"
                f"First, the advantages of {subject} are often overstated. "
                f"A careful look at the evidence shows that the expected benefits "
                f"are not as reliable as they appear.\n\n"
                f"Second, choosing {subject} comes with real trade-offs that shouldn't be ignored. "
                f"The costs — in time, resources, or opportunity — are substantial.\n\n"
                f"Third, there are viable alternatives that offer similar benefits "
                f"with less risk. It's worth considering those before committing."
            ),
            (
                f"The case for {subject} has some problems. "
                f"The promised benefits are less certain than claimed, "
                f"while the costs and risks are very real.\n\n"
                f"A more careful evaluation suggests that the alternatives "
                f"deserve serious consideration before making a decision."
            ),
            (
                f"As we wrap up, the concerns about {subject} remain unresolved. "
                f"The risks haven't been adequately addressed, and the alternatives "
                f"continue to offer a compelling path forward. "
                f"This decision deserves careful thought and a clear-eyed assessment of trade-offs."
            ),
        ]
        return rounds[min(round_num - 1, len(rounds) - 1)]

    def _demo_moderator(self, prompt: str) -> str:
        topic = extract_topic(prompt)
        round_num = extract_round(prompt)
        response_type = extract_response_type(prompt)
        focus = extract_round_focus(prompt)

        if response_type == "moderator_intro":
            intros = [
                (
                    f"Welcome to the debate.\n\n"
                    f"Today's question: {topic}\n\n"
                    f"Let's hear the opening statements."
                ),
                (
                    f"Moving to our next discussion point.\n\n"
                    f"We've heard the opening cases — now it's time to examine them more closely. "
                    f"Let's hear each side's response."
                ),
                (
                    f"Coming to the final segment.\n\n"
                    f"Each side will now present their strongest closing arguments."
                ),
            ]
            return intros[min(round_num - 1, len(intros) - 1)]

        if response_type == "moderator_summary":
            summaries = [
                (
                    f"To summarise the opening statements: the Pro side highlighted the key benefits and opportunities, "
                    f"while the Con side raised important concerns about risks and trade-offs. "
                    f"The main disagreement centres on whether the potential upside outweighs the costs."
                ),
                (
                    f"Looking at the discussion so far — Pro defended their position with evidence, "
                    f"while Con challenged its real-world applicability. "
                    f"The key open question is how the risks would play out in practice."
                ),
                (
                    f"Bringing the discussion to a close: both sides presented their strongest remaining points. "
                    f"The debate has highlighted genuine trade-offs between opportunity and caution. "
                    f"Ultimately, the decision comes down to your personal circumstances and priorities."
                ),
            ]
            return summaries[min(round_num - 1, len(summaries) - 1)]

        return (
            f"A balanced discussion of {topic} shows there are strong arguments on both sides. "
            f"The key is weighing the evidence against your specific situation."
        )

    def _demo_judge(self, prompt: str) -> str:
        topic = extract_topic(prompt)
        return json.dumps({
            "summary": (
                f"After carefully reviewing all rounds of the debate on {topic}, "
                f"both sides presented compelling arguments. The Pro side effectively demonstrated "
                f"clear benefits and long-term advantages. The Con side raised valid concerns about "
                f"risks, opportunity costs, and the need for careful planning."
            ),
            "recommendation": (
                f"Based on the debate, I recommend proceeding with {topic}, but with a "
                f"phased approach. Start with a small-scale commitment to validate assumptions, "
                f"set clear milestones, and maintain the flexibility to adjust course based on "
                f"early results. This balances the demonstrated upside with prudent risk management."
            ),
        })

    # ── Retry ───────────────────────────────────────────────────

    async def _retry(
        self,
        call: "Any",
        profile: LLMCallProfile | None = None,
    ) -> "Any":
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await call()
            except openai.OpenAIError as exc:
                if not _is_retryable(exc):
                    raise
                last_exc = exc
                if attempt < MAX_RETRIES:
                    if profile:
                        profile.retry_count += 1
                    logger.warning("LLM retry %d/%d: %s", attempt + 1, MAX_RETRIES, exc)
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
        raise last_exc  # type: ignore[misc]

    def _wrap_llm_error(self, exc: openai.OpenAIError) -> LLMError:
        if isinstance(exc, openai.APIConnectionError):
            logger.error("LLM connection failed: %s", exc)
            return LLMError(f"Cannot reach the LLM API at {self._config.base_url}. Check your network.")
        if isinstance(exc, openai.AuthenticationError):
            logger.error("LLM authentication failed: %s", exc)
            return LLMError("LLM API key was rejected. Check your LLM_API_KEY.")
        if isinstance(exc, openai.RateLimitError):
            logger.error("LLM rate limit exceeded: %s", exc)
            return LLMError("LLM API rate limit exceeded. Try again later.")
        if isinstance(exc, openai.APIStatusError):
            logger.error("LLM API error (status=%s): %s", exc.status_code, exc)
            return LLMError(f"LLM API returned status {exc.status_code}: {exc.response}")
        logger.error("LLM unexpected error: %s", exc)
        return LLMError(f"Unexpected LLM error: {exc}")

    def _get_client(self) -> openai.AsyncOpenAI:
        if self._client is None:
            self._client = openai.AsyncOpenAI(
                base_url=self._config.base_url,
                api_key=self._config.api_key,
                timeout=self._timeout,
            )
        return self._client

class LLMError(Exception):
    """Raised when an LLM operation fails for any reason."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

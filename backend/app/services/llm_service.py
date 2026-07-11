"""Provider-independent abstraction over LLM API calls.

Uses the OpenAI Python SDK under the hood but accepts any
OpenAI-compatible endpoint (OpenAI, DeepSeek, etc.) via base_url.
All configuration is read from app.config.settings.

Supports a DEMO_MODE that returns simulated responses so the full
debate flow can be demonstrated without a live LLM API key.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import openai

from app.config import settings

logger = logging.getLogger("app.services.llm_service")


@dataclass
class LLMConfig:
    """Configuration values used by LLMService.

    Defaults are read from the global Settings object at runtime,
    so the defaults here reflect what .env provides.
    """

    provider: str = settings.LLM_PROVIDER
    base_url: str = settings.LLM_BASE_URL
    api_key: str = settings.LLM_API_KEY
    model: str = settings.LLM_MODEL
    max_tokens: int = settings.LLM_MAX_TOKENS
    temperature: float = settings.LLM_TEMPERATURE


class LLMService:
    """Wraps an OpenAI-compatible LLM API behind a simple interface.

    Agents never import or call any SDK directly — they only call
    `llm_service.generate(...)`.

    The service is configured via an LLMConfig object (defaults pulled
    from environment / .env) and lazily creates the underlying
    AsyncOpenAI client on first use.
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self._config = config or LLMConfig()
        self._client: openai.AsyncOpenAI | None = None

    # ── Public API ──────────────────────────────────────────────

    async def generate(
        self,
        *,
        system_prompt: str = "",
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send a prompt to the LLM and return the generated text.

        When DEMO_MODE is enabled, returns a simulated response instead
        of making a real API call.
        """
        if settings.DEMO_MODE:
            return self._demo_response(system_prompt, prompt)

        messages: list[dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": self._config.model,
            "messages": messages,
            "temperature": temperature
            if temperature is not None
            else self._config.temperature,
            "max_tokens": max_tokens
            if max_tokens is not None
            else self._config.max_tokens,
        }

        logger.info(
            "LLM request  model=%s  temperature=%s  max_tokens=%s  messages=%d",
            kwargs["model"],
            kwargs["temperature"],
            kwargs["max_tokens"],
            len(messages),
        )

        client = self._get_client()

        try:
            response = await client.chat.completions.create(**kwargs)
        except openai.APIConnectionError as exc:
            logger.error("LLM connection failed: %s", exc)
            raise LLMError(
                f"Cannot reach the LLM API at {self._config.base_url}. "
                "Check your network connection and LLM_BASE_URL."
            ) from exc
        except openai.AuthenticationError as exc:
            logger.error("LLM authentication failed: %s", exc)
            raise LLMError("LLM API key was rejected. Check your LLM_API_KEY.") from exc
        except openai.RateLimitError as exc:
            logger.error("LLM rate limit exceeded: %s", exc)
            raise LLMError("LLM API rate limit exceeded. Try again later.") from exc
        except openai.APIStatusError as exc:
            logger.error("LLM API error (status=%s): %s", exc.status_code, exc)
            raise LLMError(
                f"LLM API returned status {exc.status_code}: {exc.response}"
            ) from exc
        except openai.OpenAIError as exc:
            logger.error("LLM unexpected error: %s", exc)
            raise LLMError(f"Unexpected LLM error: {exc}") from exc

        choice = response.choices[0]
        content = choice.message.content or ""

        logger.info(
            "LLM response  model=%s  finish_reason=%s  tokens=(input %d, output %d)  content_length=%d",
            response.model,
            choice.finish_reason,
            response.usage.prompt_tokens if response.usage else 0,
            response.usage.completion_tokens if response.usage else 0,
            len(content),
        )

        return content

    # ── Demo mode ───────────────────────────────────────────────

    def _demo_response(self, system_prompt: str, prompt: str) -> str:
        """Return a realistic simulated response based on the agent role.

        Uses the SYSTEM PROMPT for role detection since the user prompt
        contains previous round content (including other agents' output)
        that would confuse a content-based classifier.
        """
        sys_lower = system_prompt.lower()

        if "moderator" in sys_lower:
            return self._demo_moderator(prompt)
        if "judge" in sys_lower or "verdict" in sys_lower or "impartial" in sys_lower:
            return self._demo_judge(prompt)
        if "against" in sys_lower or "challenger" in sys_lower:
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
        """Simulated pro (FOR) argument."""
        topic = self._extract_topic(prompt)
        round_num = self._extract_round(prompt)
        rounds = [
            (
                f"**Opening Argument — {topic}**\n\n"
                f"1. **Career Advancement**: Pursuing {topic} would significantly enhance your professional trajectory. "
                f"Data consistently shows that those who invest in this direction see measurable improvements.\n\n"
                f"2. **Personal Growth**: The learning journey itself develops resilience, critical thinking, and "
                f"a broader perspective that benefits all areas of life.\n\n"
                f"3. **Network Effects**: Engaging with this space connects you with motivated, "
                f"like-minded individuals who can become lifelong collaborators.\n\n"
                f"4. **Future-Proofing**: The trends strongly favour those who take this step now rather than later."
            ),
            (
                f"**Rebuttal — {topic} (Round 2)**\n\n"
                f"Addressing the counter-arguments raised:\n\n"
                f"1. **On costs**: While the upfront investment is real, the long-term return on investment "
                f"consistently outstrips the initial outlay within 2-3 years.\n\n"
                f"2. **On opportunity cost**: The question isn't whether there are other good options — "
                f"it's whether this path offers unique advantages that others don't. It does.\n\n"
                f"3. **On timing**: Market conditions and personal circumstances align favourably right now. "
                f"Waiting often means higher barriers later.\n\n"
                f"The key is to proceed strategically: start small, validate early, and scale gradually."
            ),
            (
                f"**Closing Argument — {topic}**\n\n"
                f"Throughout this debate, the case FOR has remained clear:\n\n"
                f"1. The evidence strongly supports that this path leads to better outcomes on average.\n"
                f"2. The risks identified by the opposition are real but manageable with proper planning.\n"
                f"3. The upside potential far outweighs the downsides when executed thoughtfully.\n\n"
                f"I recommend moving forward with a concrete plan: define milestones, set aside dedicated time, "
                f"and leverage the resources available."
            ),
        ]
        return rounds[min(round_num - 1, len(rounds) - 1)]

    def _demo_con(self, prompt: str) -> str:
        """Simulated con (AGAINST) argument."""
        topic = self._extract_topic(prompt)
        round_num = self._extract_round(prompt)
        rounds = [
            (
                f"**Opening Argument — Against {topic}**\n\n"
                f"1. **Significant Investment**: This path demands substantial time, energy, and financial "
                f"resources that could be directed elsewhere with higher certainty of return.\n\n"
                f"2. **Opportunity Cost**: Every hour spent here is an hour not spent on alternatives that may "
                f"offer a better risk/reward profile given your current situation.\n\n"
                f"3. **Not for Everyone**: The success stories create survivorship bias. Many who try this path "
                f"find that it doesn't meet their expectations or suit their circumstances.\n\n"
                f"4. **Burnout Risk**: The intense focus required can lead to diminished performance in "
                f"other important areas of life."
            ),
            (
                f"**Rebuttal — Against {topic} (Round 2)**\n\n"
                f"Let me address the proponent's claims:\n\n"
                f"1. **On career benefits**: The claimed advantages are overstated and highly dependent on "
                f"circumstances that may not apply to your situation.\n\n"
                f"2. **On personal growth**: Growth can be achieved through many less risky, less expensive means. "
                f"This isn't the only — or best — path to development.\n\n"
                f"3. **On timing**: Rushing into decisions based on 'favourable timing' often leads to regret. "
                f"A more measured approach allows for better information gathering.\n\n"
                f"Consider starting with a small-scale experiment before committing fully."
            ),
            (
                f"**Closing Argument — Against {topic}**\n\n"
                f"The case AGAINST remains strong:\n\n"
                f"1. The risks are real and often understated by advocates.\n"
                f"2. Alternatives exist that offer similar benefits with lower downside.\n"
                f"3. A 'wait and assess' approach preserves optionality.\n\n"
                f"My recommendation: don't rush. Take 3-6 months to explore on a small scale, "
                f"gather more data, and make an informed decision only when the picture is clearer."
            ),
        ]
        return rounds[min(round_num - 1, len(rounds) - 1)]

    def _demo_moderator(self, prompt: str) -> str:
        """Simulated moderator steer."""
        round_num = self._extract_round(prompt)
        rounds = [
            (
                "Welcome to today's debate. This is a fascinating and nuanced topic with strong cases on both sides.\n\n"
                "**Steer for Round 1**: I'd like both sides to focus their opening arguments on the core practical "
                "implications. Pro, please make the positive case with concrete benefits. Con, please identify the "
                "key risks and trade-offs. Keep your arguments evidence-informed and actionable."
            ),
            (
                "An excellent first round with substantive arguments from both sides.\n\n"
                "**Steer for Round 2**: Pro, please address the cost concerns raised by Con. Con, please respond to "
                "the career advantages the Pro outlined. I'd like both sides to dig deeper into the long-term "
                "implications and challenge each other's assumptions."
            ),
            (
                "Round 2 sharpened the debate considerably. Both sides have made compelling points.\n\n"
                "**Steer for Round 3**: This is your final opportunity. Pro, make your closing case — summarise why "
                "the benefits decisively outweigh the costs. Con, deliver your closing argument — explain why caution "
                "and alternative paths deserve serious consideration."
            ),
        ]
        return rounds[min(round_num - 1, len(rounds) - 1)]

    def _demo_judge(self, prompt: str) -> str:
        """Simulated judge verdict."""
        topic = self._extract_topic(prompt)
        return (
            f'After carefully reviewing three rounds of debate on **"{topic}"**, here is my analysis:\n\n'
            f"The **Pro side** made a strong case centred on career advancement, personal growth, "
            f"network effects, and future-proofing. Their arguments were well-structured and grounded "
            f"in practical benefits.\n\n"
            f"The **Con side** raised legitimate concerns about investment costs, opportunity costs, "
            f"survivorship bias, and burnout risk. Their cautions about a measured approach are worth heeding.\n\n"
            f"Both sides presented valid points. The Pro's case is compelling if you have the capacity "
            f"and resources to commit fully. The Con's warnings are particularly valuable for those "
            f"with constrained time or financial resources.\n\n"
            f"Pursue this path, but start with a small-scale commitment — a trial period or "
            f"part-time engagement — before going all in. This approach captures the upside while "
            f"limiting downside risk. Set clear milestones and reassess at each one. The evidence "
            f"suggests that thoughtful, incremental commitment is the optimal strategy."
        )

    # ── Internal helpers ────────────────────────────────────────

    def _get_client(self) -> openai.AsyncOpenAI:
        """Lazily initialise and return the AsyncOpenAI client."""
        if self._client is None:
            self._client = openai.AsyncOpenAI(
                base_url=self._config.base_url,
                api_key=self._config.api_key,
            )
        return self._client

    @staticmethod
    def _extract_topic(prompt: str) -> str:
        """Extract the debate topic from a prompt string."""
        for line in prompt.split("\n"):
            if line.lower().startswith("debate topic:"):
                return line.split(":", 1)[1].strip()
            if line.lower().startswith("topic:"):
                return line.split(":", 1)[1].strip()
        return "this topic"

    @staticmethod
    def _extract_round(prompt: str) -> int:
        """Extract the round number from a prompt string."""
        for line in prompt.split("\n"):
            line = line.strip()
            if line.lower().startswith("round:"):
                parts = line.split(":", 1)
                try:
                    return int(parts[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass
            if line.lower().startswith("round number:"):
                parts = line.split(":", 1)
                try:
                    return int(parts[1].strip())
                except (ValueError, IndexError):
                    pass
        return 1


class LLMError(Exception):
    """Raised when an LLM operation fails for any reason.

    Wraps provider-specific errors into a single exception type
    so callers never need to import or catch SDK-specific exceptions.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

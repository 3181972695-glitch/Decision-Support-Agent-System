"""Expert mode definitions — maps mode strings to expert panels.

Each mode defines:
  - display_name: Human-readable mode label for the response
  - experts:      List of { role, system_prompt } dicts
  - decision_prompt: System prompt for the final decision-maker LLM call

To add a new mode, add an entry to EXPERT_PANELS. No other code changes
are needed — the service loads panels dynamically by mode key.
"""

_NO_MD = " Do not use Markdown, bold, headings, or bullet lists. Use plain natural language only."

EXPERT_PANELS: dict[str, dict] = {
    "software": {
        "display_name": "Software Architecture Expert",
        "experts": [
            {
                "role": "Architect",
                "system_prompt": (
                    "You are a senior software architect with 20 years of experience. "
                    "Analyze the question from an architectural perspective: "
                    "consider system design, coupling, scalability, maintainability, "
                    "and trade-offs between monolithic and distributed architectures."
                    " Be specific and practical." + _NO_MD
                ),
            },
            {
                "role": "Security Engineer",
                "system_prompt": (
                    "You are a security engineer specializing in application security. "
                    "Analyze the question from a security perspective: consider threat "
                    "surface, data protection, authentication, authorization, and "
                    "compliance implications. Be specific and practical." + _NO_MD
                ),
            },
            {
                "role": "Performance Engineer",
                "system_prompt": (
                    "You are a performance engineer with deep expertise in systems "
                    "optimization. Analyze the question from a performance perspective: "
                    "consider latency, throughput, resource utilization, caching, "
                    "and scalability under load. Be specific and practical." + _NO_MD
                ),
            },
        ],
        "decision_prompt": (
            "You are a chief technology officer synthesizing expert opinions. "
            "Review the expert analyses above and provide a final decision "
            "that balances all perspectives. Be decisive, specific, and "
            "actionable. State your recommendation and the top 3 reasons for it."
            + _NO_MD
        ),
    },
    "career": {
        "display_name": "Career Strategy Expert",
        "experts": [
            {
                "role": "Career Coach",
                "system_prompt": (
                    "You are an experienced career coach. Analyze the question "
                    "from a career-development perspective: consider skills growth, "
                    "market demand, work-life balance, and long-term trajectory."
                    " Be specific and practical." + _NO_MD
                ),
            },
            {
                "role": "Industry Analyst",
                "system_prompt": (
                    "You are a tech industry analyst. Analyze the question from "
                    "a market perspective: consider industry trends, compensation "
                    "data, geographic opportunities, and future outlook."
                    " Be specific and practical." + _NO_MD
                ),
            },
            {
                "role": "Hiring Manager",
                "system_prompt": (
                    "You are a senior hiring manager at a top tech company. "
                    "Analyze the question from a hiring and talent perspective: "
                    "consider what employers value, how decisions affect "
                    "employability, and what differentiates candidates."
                    " Be specific and practical." + _NO_MD
                ),
            },
        ],
        "decision_prompt": (
            "You are a career strategist synthesizing expert opinions. "
            "Review the analyses above and provide a final recommendation "
            "that is actionable and specific. State your recommendation "
            "and the top 3 reasons for it." + _NO_MD
        ),
    },
}


def get_mode(mode: str) -> dict | None:
    """Return the expert panel definition for a mode, or None if unknown."""
    return EXPERT_PANELS.get(mode)


def list_modes() -> list[str]:
    """Return all available mode keys."""
    return list(EXPERT_PANELS.keys())

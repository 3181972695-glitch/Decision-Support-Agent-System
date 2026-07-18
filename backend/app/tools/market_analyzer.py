"""Market analyzer tool — provides market information about companies and topics.

For MVP, returns structured mock analysis based on keyword matching.
"""

import logging
import re

from app.tools.tool_registry import register_tool

logger = logging.getLogger("app.tools.market_analyzer")

_MARKET_DATA: dict[str, dict] = {
    "aws": {
        "name": "Amazon Web Services (AWS)",
        "market_share": "32% of cloud infrastructure market (2025)",
        "revenue": "$100B+ annual run rate",
        "trend": "Leader in cloud, growing at 15-20% YoY",
        "key_competitors": ["Microsoft Azure (23%)", "Google Cloud (11%)", "Oracle Cloud (4%)"],
    },
    "azure": {
        "name": "Microsoft Azure",
        "market_share": "23% of cloud infrastructure market (2025)",
        "revenue": "$80B+ annual run rate",
        "trend": "Strong growth at 20-25% YoY, enterprise-focused",
        "key_competitors": ["AWS (32%)", "Google Cloud (11%)"],
    },
    "google cloud": {
        "name": "Google Cloud Platform (GCP)",
        "market_share": "11% of cloud infrastructure market (2025)",
        "revenue": "$40B+ annual run rate",
        "trend": "Growing at 25-30% YoY, strong in AI/ML",
        "key_competitors": ["AWS (32%)", "Azure (23%)"],
    },
    "kubernetes": {
        "name": "Kubernetes / Container Orchestration",
        "market_size": "$5B+ market, growing at 25% CAGR",
        "adoption": "96% of organizations are using or evaluating Kubernetes",
        "trend": "Industry standard for container orchestration",
        "key_players": ["Google (creator)", "Red Hat/IBM", "AWS (EKS)", "Azure (AKS)", "GCP (GKE)"],
    },
}


@register_tool(
    name="market_analyzer",
    description="Get market analysis for a company, technology, or topic. Returns market share, trends, and competitive landscape.",
    parameters={
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The company or topic to analyze, e.g. 'AWS', 'Kubernetes', 'AI coding tools'",
            }
        },
        "required": ["topic"],
    },
)
async def run_market_analyzer(topic: str) -> str:
    """Analyze a company or technology and return market information."""
    logger.info("[TOOL] market_analyzer(%r)", topic)
    topic_lower = topic.lower()

    # Direct lookup
    for key, data in _MARKET_DATA.items():
        if key in topic_lower:
            lines = [f"Market Analysis: {data['name']}", ""]
            for k, v in data.items():
                if k != "name":
                    label = k.replace("_", " ").title()
                    if isinstance(v, list):
                        lines.append(f"  {label}:")
                        for item in v:
                            lines.append(f"    - {item}")
                    else:
                        lines.append(f"  {label}: {v}")
                lines.append("")
            return "\n".join(lines)

    # Generic response for unknown topics
    return (
        f"Market Analysis for: {topic}\n\n"
        f"'{topic}' is an active market segment with growing interest. "
        f"Multiple vendors and open-source solutions are competing in this space. "
        f"Recommended: conduct a detailed survey of the current landscape "
        f"including adoption trends, total cost of ownership, and vendor lock-in risks."
    )

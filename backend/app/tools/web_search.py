"""Web search tool — performs a simulated web search.

In a production system this would call an actual search API.
For MVP, returns structured mock results covering common topics.
"""

import logging
import re

from app.tools.tool_registry import register_tool

logger = logging.getLogger("app.tools.web_search")

# Knowledge base for common queries
_KNOWLEDGE: dict[str, list[str]] = {
    "microservices": [
        "Microservices architecture decomposes applications into independently deployable services.",
        "Netflix, Amazon, and Uber have successfully migrated from monoliths to microservices.",
        "Common challenges include network latency, data consistency, and operational complexity.",
        "The strangler fig pattern is a recommended gradual migration strategy.",
    ],
    "kubernetes": [
        "Kubernetes is an open-source container orchestration platform originally developed by Google.",
        "Kubernetes automates deployment, scaling, and management of containerized applications.",
        "Major cloud providers offer managed Kubernetes services (EKS, AKS, GKE).",
    ],
    "ai": [
        "AI adoption in enterprises grew by 270% over the past four years.",
        "Common AI use cases include customer service automation, code generation, and data analysis.",
        "Key concerns include data privacy, model bias, and integration with existing systems.",
    ],
    "python": [
        "Python is the 2nd most popular programming language according to the TIOBE index.",
        "Python dominates in data science, ML/AI, and backend web development.",
        "Python 3.13 introduced significant performance improvements and free-threaded mode.",
    ],
    "rust": [
        "Rust has been the most loved language on Stack Overflow surveys for 8 consecutive years.",
        "Rust provides memory safety without garbage collection, making it ideal for systems programming.",
        "Major adopters include Microsoft, Google, AWS, and the Linux kernel project.",
    ],
    "startup": [
        "Approximately 90% of startups fail, with the most common reason being lack of market need.",
        "The median time to profitability for VC-backed startups is 5-7 years.",
        "Lean startup methodology emphasizes build-measure-learn cycles and MVP development.",
    ],
}


def _search(query: str) -> list[dict]:
    """Search the knowledge base for relevant results."""
    query_lower = query.lower()
    results: list[dict] = []

    # Score each knowledge entry by keyword overlap
    for topic, entries in _KNOWLEDGE.items():
        for entry in entries:
            entry_lower = entry.lower()
            score = 0
            for word in set(re.findall(r'\w+', query_lower)):
                if word in entry_lower:
                    score += 1
            if score > 0:
                results.append({
                    "title": topic.capitalize(),
                    "snippet": entry,
                    "relevance": score,
                })

    # Sort by relevance
    results.sort(key=lambda x: -x["relevance"])
    return results[:5]


@register_tool(
    name="web_search",
    description="Search the web for information on a topic. Returns up to 5 relevant results with snippets.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query, e.g. 'microservices migration benefits'",
            }
        },
        "required": ["query"],
    },
)
async def run_web_search(query: str) -> str:
    """Search knowledge base and return formatted results."""
    logger.info("[TOOL] web_search(%r)", query)
    results = _search(query)
    if not results:
        return f"No results found for '{query}'. The knowledge base has limited coverage."

    lines = [f"Search results for: {query}", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['snippet']}")
        lines.append("")
    return "\n".join(lines)

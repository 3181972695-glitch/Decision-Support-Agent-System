"""Code analyzer tool — estimates codebase statistics.

For MVP, returns simulated analysis based on description patterns.
A production version would use a real code analysis pipeline.
"""

import logging
import re

from app.tools.tool_registry import register_tool

logger = logging.getLogger("app.tools.code_analyzer")


@register_tool(
    name="code_analyzer",
    description="Analyze a codebase or repository. Returns estimated statistics about code complexity, language usage, and structure.",
    parameters={
        "type": "object",
        "properties": {
            "repository": {
                "type": "string",
                "description": "Description or path of the codebase to analyze, e.g. 'monolithic Rails e-commerce app'",
            }
        },
        "required": ["repository"],
    },
)
async def run_code_analyzer(repository: str) -> str:
    """Analyze a repository description and return estimated statistics."""
    logger.info("[TOOL] code_analyzer(%r)", repository)
    repo_lower = repository.lower()

    # Estimate language based on description
    languages = []
    if "python" in repo_lower:
        languages.append(("Python", 45))
    if "javascript" in repo_lower or "typescript" in repo_lower or "js" in repo_lower:
        languages.append(("JavaScript/TypeScript", 25))
    if "rails" in repo_lower or "ruby" in repo_lower:
        languages.append(("Ruby", 35))
    if "java" in repo_lower:
        languages.append(("Java", 50))
    if "go" in repo_lower or "golang" in repo_lower:
        languages.append(("Go", 30))
    if "rust" in repo_lower:
        languages.append(("Rust", 25))
    if "react" in repo_lower:
        languages.append(("JSX/TSX", 15))
    if "sql" in repo_lower or "database" in repo_lower:
        languages.append(("SQL", 10))

    if not languages:
        languages = [("Unknown", 100)]

    # Normalize percentages
    total = sum(p for _, p in languages)
    languages = [(lang, round(p / total * 100)) for lang, p in languages]

    # Estimate scale
    if any(w in repo_lower for w in ["large", "enterprise", "complex", "monolith"]):
        est_files = "5000-15000"
        est_lines = "200000-800000"
        team_size = "10-40"
    elif any(w in repo_lower for w in ["medium", "standard"]):
        est_files = "500-2000"
        est_lines = "30000-150000"
        team_size = "5-15"
    else:
        est_files = "50-300"
        est_lines = "5000-40000"
        team_size = "2-8"

    lines = [
        f"Code analysis for: {repository}",
        "",
        f"Estimated files:  {est_files}",
        f"Estimated lines:  {est_lines}",
        f"Estimated team:   {team_size} developers",
        "",
        "Language breakdown:",
    ]
    for lang, pct in languages:
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        lines.append(f"  {lang:25s} {bar} {pct}%")

    return "\n".join(lines)

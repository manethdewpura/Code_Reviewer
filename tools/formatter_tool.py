from __future__ import annotations

from collections import defaultdict
from typing import Any


def generate_refactor_suggestions(issues: list[dict[str, Any]]) -> dict[str, Any]:
    """Formats improvements into a structured per-file suggestion map.

    Args:
        issues: List of issue dicts, typically from other agents/tools.

    Returns:
        A dict containing grouped suggestions per file and a short summary.
    """
    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for issue in issues:
        file = str(issue.get("file", "unknown"))
        by_file[file].append(issue)

    suggestions = {
        "files": dict(by_file),
        "summary": {
            "files_with_suggestions": len(by_file),
            "suggestion_count": sum(len(v) for v in by_file.values()),
        },
    }
    return suggestions


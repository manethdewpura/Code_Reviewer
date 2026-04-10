from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from radon.complexity import cc_visit
from radon.metrics import h_visit


@dataclass(frozen=True)
class ComplexityMetrics:
    cyclomatic_avg: float
    cyclomatic_max: int
    cyclomatic_functions: list[dict[str, Any]]
    halstead_total: dict[str, Any] | None


def _halstead_total_to_dict(total: Any) -> dict[str, Any]:
    # Radon returns a HalsteadReport-like object that may not expose `__dict__`.
    fields = [
        "h1",
        "h2",
        "N1",
        "N2",
        "vocabulary",
        "length",
        "calculated_length",
        "volume",
        "difficulty",
        "effort",
        "time",
        "bugs",
    ]
    out: dict[str, Any] = {}
    for k in fields:
        if hasattr(total, k):
            out[k] = getattr(total, k)
    return out


def calculate_complexity(code: str, *, language: str = "python") -> dict[str, Any]:
    """Returns cyclomatic complexity metrics.

    Notes:
        - Fully supports Python via `radon`.
        - For non-Python files, returns a minimal placeholder structure.
    """
    lang = language.lower().strip()
    if lang not in {"py", "python"}:
        return {
            "language": lang,
            "supported": False,
            "reason": "Only Python complexity is computed with radon in this baseline.",
        }

    blocks = cc_visit(code)
    scores = [b.complexity for b in blocks] or [0]
    funcs = [
        {
            "name": b.name,
            "lineno": b.lineno,
            "endline": getattr(b, "endline", None),
            "complexity": b.complexity,
            "type": b.__class__.__name__,
        }
        for b in blocks
    ]
    halstead = h_visit(code)
    metrics = ComplexityMetrics(
        cyclomatic_avg=sum(scores) / max(1, len(scores)),
        cyclomatic_max=max(scores),
        cyclomatic_functions=funcs,
        halstead_total=_halstead_total_to_dict(halstead.total) if halstead and halstead.total else None,
    )
    out = asdict(metrics)
    out["language"] = "python"
    out["supported"] = True
    return out


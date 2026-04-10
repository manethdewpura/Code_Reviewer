from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


Severity = Literal["low", "medium", "high", "critical"]
FindingType = Literal["quality", "security", "refactor"]


@dataclass(frozen=True)
class Finding:
    file: str
    type: FindingType
    severity: Severity
    title: str
    details: str
    recommendation: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewState:
    project_root: str
    model: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    project_files: list[str] = field(default_factory=list)
    file_contents: dict[str, str] = field(default_factory=dict)

    quality_findings: list[Finding] = field(default_factory=list)
    security_findings: list[Finding] = field(default_factory=list)
    refactor_findings: list[Finding] = field(default_factory=list)

    final_report: dict[str, Any] = field(default_factory=dict)
    run_dir: str | None = None


from __future__ import annotations

from typing import Any, Literal, TypedDict


Severity = Literal["low", "medium", "high", "critical"]
FindingType = Literal["quality", "security", "refactor"]


class FindingDict(TypedDict, total=False):
    file: str
    type: FindingType
    severity: Severity
    title: str
    details: str
    recommendation: str
    evidence: dict[str, Any]


class ReviewStateDict(TypedDict, total=False):
    project_root: str
    model: str
    created_at: str
    run_dir: str

    project_files: list[str]
    file_contents: dict[str, str]

    quality_findings: list[FindingDict]
    security_findings: list[FindingDict]
    refactor_findings: list[FindingDict]

    final_report: dict[str, Any]


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


class ExecutionPlanDict(TypedDict, total=False):
    run_quality: bool
    run_security: bool
    run_refactor: bool


class ReviewStateDict(TypedDict, total=False):
    project_root: str
    model: str
    created_at: str
    run_dir: str
    run_id: str
    active_span_id: str

    project_files: list[str]
    file_contents: dict[str, str]
    execution_plan: ExecutionPlanDict

    quality_findings: list[FindingDict]
    security_findings: list[FindingDict]
    refactor_findings: list[FindingDict]

    final_report: dict[str, Any]


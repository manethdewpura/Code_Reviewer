from __future__ import annotations

from pathlib import Path

from agents.state_types import FindingDict, ReviewStateDict
from observability.tracer import JsonlTracer
from schemas.contracts import (
    ComplexityResultModel,
    QualityResponseModel,
    normalize_quality_response,
    safe_validate,
)
from tools.complexity_tool import calculate_complexity
from tools.ollama_client import ollama_chat_json


SYSTEM_PROMPT = """
You are the Code Quality Agent in a multi-agent code review system.

Goal: identify code quality issues and give practical recommendations.
Constraints:
- Only use the provided file metrics and snippets; do not invent file contents.
- Output MUST be valid JSON only.
- Prefer actionable, specific recommendations (refactor targets, complexity hotspots).
""".strip()


def _basic_metrics(code: str) -> dict[str, int]:
    lines = code.splitlines()
    non_empty = sum(1 for l in lines if l.strip())
    return {"lines": len(lines), "non_empty_lines": non_empty}


def code_quality_agent(state: ReviewStateDict) -> ReviewStateDict:
    tracer = JsonlTracer(state["run_dir"], run_id=state.get("run_id"), component="quality")
    parent_span_id = state.get("active_span_id")
    span_id = tracer.start_span("quality", parent_span_id=parent_span_id, payload={"files": len(state.get("project_files", []))})

    model = state["model"]
    findings: list[FindingDict] = []

    for fp, code in state.get("file_contents", {}).items():
        ext = Path(fp).suffix.lower()
        metrics = _basic_metrics(code)

        # Deterministic rule-based findings (tool-free)
        if metrics["lines"] > 400:
            findings.append(
                {
                    "file": fp,
                    "type": "quality",
                    "severity": "medium",
                    "title": "Large file",
                    "details": f"File has {metrics['lines']} lines.",
                    "recommendation": "Split into smaller modules and move cohesive logic into separate files.",
                    "evidence": {"lines": metrics["lines"]},
                }
            )

        # Tool: complexity (Python only)
        if ext == ".py":
            comp = calculate_complexity(code, language="python")
            valid_comp = safe_validate(ComplexityResultModel, comp)
            if not valid_comp:
                tracer.emit("tool.calculate_complexity.error", {"file": fp, "result": comp}, level="ERROR", span_id=span_id, parent_span_id=parent_span_id)
                tracer.emit_metric("tool.calculate_complexity.validation_error.count")
                continue
            comp = valid_comp.model_dump()
            tracer.emit("tool.calculate_complexity", {"file": fp, "result": comp}, span_id=span_id, parent_span_id=parent_span_id)
            tracer.emit_metric("tool.calculate_complexity.count")

            if comp.get("supported") and comp.get("cyclomatic_max", 0) >= 15:
                hotspots = sorted(comp.get("cyclomatic_functions", []), key=lambda x: x.get("complexity", 0), reverse=True)[:3]
                findings.append(
                    {
                        "file": fp,
                        "type": "quality",
                        "severity": "high",
                        "title": "High cyclomatic complexity",
                        "details": f"Max cyclomatic complexity is {comp.get('cyclomatic_max')}.",
                        "recommendation": "Split complex functions, reduce nesting, and extract helper methods for decision branches.",
                        "evidence": {"hotspots": hotspots, "cyclomatic_max": comp.get("cyclomatic_max")},
                    }
                )

        # LLM enrichment for very large / complex files (bounded context)
        if (metrics["lines"] >= 250) or (ext == ".py" and any(f.get("file") == fp and f.get("title") == "High cyclomatic complexity" for f in findings)):
            user = {
                "file": fp,
                "extension": ext,
                "metrics": metrics,
                "snippet_head": code[:2000],
            }
            schema_hint = {
                "issues": [
                    {
                        "title": "string",
                        "severity": "low|medium|high",
                        "details": "string",
                        "recommendation": "string",
                    }
                ]
            }
            tracer.emit("quality.llm.request", {"file": fp, "model": model})
            resp = ollama_chat_json(
                model=model,
                system=SYSTEM_PROMPT,
                user=f"Analyze this file summary and return code quality issues.\n\n{user}",
                schema_hint=schema_hint,
                temperature=0.2,
            )
            normalized_resp = normalize_quality_response(resp)
            valid_resp = safe_validate(QualityResponseModel, normalized_resp)
            if not valid_resp:
                tracer.emit("quality.llm.response.error", {"file": fp, "response": resp}, level="ERROR", span_id=span_id, parent_span_id=parent_span_id)
                tracer.emit_metric("quality.llm.validation_error.count")
                continue
            tracer.emit("quality.llm.response", {"file": fp, "issues": len(valid_resp.issues)}, span_id=span_id, parent_span_id=parent_span_id)
            tracer.emit_metric("quality.llm.calls.count")
            for issue in valid_resp.issues:
                findings.append(
                    {
                        "file": fp,
                        "type": "quality",
                        "severity": issue.severity,
                        "title": issue.title or "Code quality issue",
                        "details": issue.details or "",
                        "recommendation": issue.recommendation or "",
                        "evidence": {"source": "llm_enrichment"},
                    }
                )

    state["quality_findings"] = findings
    tracer.emit_metric("quality.findings.total", float(len(findings)))
    tracer.end_span("quality", span_id=span_id, parent_span_id=parent_span_id, payload={"findings": len(findings)})
    return state
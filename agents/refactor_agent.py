from __future__ import annotations

from agents.state_types import FindingDict, ReviewStateDict
from observability.tracer import JsonlTracer
from schemas.contracts import (
    RefactorResponseModel,
    RefactorSuggestionsModel,
    normalize_refactor_response,
    safe_validate,
)
from tools.formatter_tool import generate_refactor_suggestions
from tools.ollama_client import ollama_chat_json


SYSTEM_PROMPT = """
You are the Refactoring Agent in a multi-agent code review system.

Goal: propose refactoring steps that improve readability, modularity, and maintainability.
Constraints:
- Base recommendations only on provided findings and short snippets (no hallucinations).
- Prefer small, safe refactors (rename, extract function, split modules, add validation).
- Output MUST be valid JSON only.
""".strip()


def refactor_agent(state: ReviewStateDict) -> ReviewStateDict:
    tracer = JsonlTracer(state["run_dir"], run_id=state.get("run_id"), component="refactor")
    parent_span_id = state.get("active_span_id")
    span_id = tracer.start_span(
        "refactor",
        parent_span_id=parent_span_id,
        payload={
            "quality_findings": len(state.get("quality_findings", [])),
            "security_findings": len(state.get("security_findings", [])),
        },
    )

    model = state["model"]
    combined: list[dict] = []
    for f in state.get("quality_findings", []):
        combined.append({"file": f.get("file"), "title": f.get("title"), "recommendation": f.get("recommendation"), "type": "quality"})
    for f in state.get("security_findings", []):
        combined.append({"file": f.get("file"), "title": f.get("title"), "recommendation": f.get("recommendation"), "type": "security"})

    structured = generate_refactor_suggestions(combined)
    valid_structured = safe_validate(RefactorSuggestionsModel, structured)
    if not valid_structured:
        tracer.emit("tool.generate_refactor_suggestions.validation_error", {"result": structured}, level="ERROR", span_id=span_id, parent_span_id=parent_span_id)
        tracer.emit_metric("tool.generate_refactor_suggestions.validation_error.count")
        structured = {"files": {}, "summary": {"files_with_suggestions": 0, "suggestion_count": 0}}
    else:
        structured = valid_structured.model_dump()
    tracer.emit("tool.generate_refactor_suggestions", {"result": structured.get("summary")}, span_id=span_id, parent_span_id=parent_span_id)
    tracer.emit_metric("tool.generate_refactor_suggestions.count")

    # LLM: convert grouped issues into a concrete refactor plan
    schema_hint = {
        "plan": [
            {
                "file": "string",
                "steps": ["string"],
                "risk": "low|medium|high",
            }
        ]
    }
    tracer.emit("refactor.llm.request", {"model": model})
    resp = ollama_chat_json(
        model=model,
        system=SYSTEM_PROMPT,
        user=f"Turn these grouped findings into a refactor plan.\n\n{structured}",
        schema_hint=schema_hint,
        temperature=0.2,
    )
    normalized_resp = normalize_refactor_response(resp)
    valid_resp = safe_validate(RefactorResponseModel, normalized_resp)
    if not valid_resp:
        tracer.emit("refactor.llm.response.error", {"response": resp}, level="ERROR", span_id=span_id, parent_span_id=parent_span_id)
        tracer.emit_metric("refactor.llm.validation_error.count")
        valid_resp = RefactorResponseModel(plan=[])
    else:
        tracer.emit("refactor.llm.response", {"plan_items": len(valid_resp.plan)}, span_id=span_id, parent_span_id=parent_span_id)
        tracer.emit_metric("refactor.llm.calls.count")

    findings: list[FindingDict] = []
    for item in valid_resp.plan:
        file = item.file or "unknown"
        steps = item.steps or []
        risk = item.risk or "low"
        findings.append(
            {
                "file": file,
                "type": "refactor",
                "severity": "low" if risk == "low" else "medium" if risk == "medium" else "high",
                "title": "Refactor plan",
                "details": "Concrete refactor steps derived from earlier agent findings.",
                "recommendation": "\n".join(f"- {s}" for s in steps) if isinstance(steps, list) else str(steps),
                "evidence": {"risk": risk},
            }
        )

    state["refactor_findings"] = findings
    tracer.emit_metric("refactor.findings.total", float(len(findings)))
    tracer.end_span("refactor", span_id=span_id, parent_span_id=parent_span_id, payload={"findings": len(findings)})
    return state
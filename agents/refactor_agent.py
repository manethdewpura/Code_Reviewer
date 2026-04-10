from __future__ import annotations

from agents.state_types import FindingDict, ReviewStateDict
from observability.tracer import JsonlTracer
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
    tracer = JsonlTracer(state["run_dir"])
    tracer.emit(
        "refactor.start",
        {
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
    tracer.emit("tool.generate_refactor_suggestions", {"result": structured.get("summary")})

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
    tracer.emit("refactor.llm.response", {"response": resp})

    findings: list[FindingDict] = []
    for item in (resp.get("plan") or []) if isinstance(resp, dict) else []:
        file = item.get("file") or "unknown"
        steps = item.get("steps") or []
        risk = item.get("risk") or "low"
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
    tracer.emit("refactor.done", {"findings": len(findings)})
    return state


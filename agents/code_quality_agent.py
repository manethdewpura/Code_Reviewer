from __future__ import annotations

from pathlib import Path

from agents.state_types import FindingDict, ReviewStateDict
from observability.tracer import JsonlTracer
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
    tracer = JsonlTracer(state["run_dir"])
    tracer.emit("quality.start", {"files": len(state.get("project_files", []))})

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
            tracer.emit("tool.calculate_complexity", {"file": fp, "result": comp})

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
            tracer.emit("quality.llm.response", {"file": fp, "response": resp})
            for issue in (resp.get("issues") or []) if isinstance(resp, dict) else []:
                findings.append(
                    {
                        "file": fp,
                        "type": "quality",
                        "severity": (issue.get("severity") or "low"),
                        "title": issue.get("title") or "Code quality issue",
                        "details": issue.get("details") or "",
                        "recommendation": issue.get("recommendation") or "",
                        "evidence": {"source": "llm_enrichment"},
                    }
                )

    state["quality_findings"] = findings
    tracer.emit("quality.done", {"findings": len(findings)})
    return state


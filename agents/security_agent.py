from __future__ import annotations

from agents.state_types import FindingDict, ReviewStateDict
from observability.tracer import JsonlTracer
from schemas.contracts import SecurityHitModel, SecurityResponseModel, safe_validate
from tools.ollama_client import ollama_chat_json
from tools.security_scanner import scan_security_risks


SYSTEM_PROMPT = """
You are the Security Agent in a multi-agent code review system.

Goal: detect security risks in the provided code snippet/scan results and propose mitigations.
Constraints:
- Do not claim a vulnerability is exploitable without evidence; use cautious language.
- Do not invent dependencies, frameworks, or endpoints that are not shown.
- Output MUST be valid JSON only.
""".strip()


def security_agent(state: ReviewStateDict) -> ReviewStateDict:
    tracer = JsonlTracer(state["run_dir"], run_id=state.get("run_id"), component="security")
    parent_span_id = state.get("active_span_id")
    span_id = tracer.start_span("security", parent_span_id=parent_span_id, payload={"files": len(state.get("project_files", []))})

    model = state["model"]
    findings: list[FindingDict] = []

    for fp, code in state.get("file_contents", {}).items():
        raw_hits = scan_security_risks(code)
        hits: list[dict] = []
        for h in raw_hits:
            valid_hit = safe_validate(SecurityHitModel, h)
            if not valid_hit:
                tracer.emit("tool.scan_security_risks.validation_error", {"file": fp, "hit": h}, level="ERROR", span_id=span_id, parent_span_id=parent_span_id)
                tracer.emit_metric("tool.scan_security_risks.validation_error.count")
                continue
            hits.append(valid_hit.model_dump())
        tracer.emit("tool.scan_security_risks", {"file": fp, "hits": len(hits)}, span_id=span_id, parent_span_id=parent_span_id)
        tracer.emit_metric("tool.scan_security_risks.count")

        for h in hits:
            findings.append(
                {
                    "file": fp,
                    "type": "security",
                    "severity": h.get("severity", "medium"),
                    "title": h.get("title", "Security risk"),
                    "details": f"Matched rule {h.get('rule_id')}.",
                    "recommendation": _recommendation_for_rule(h.get("rule_id")),
                    "evidence": h.get("evidence", {}),
                }
            )

        # LLM enrichment only if we have hits (keeps runtime bounded)
        if hits:
            user = {
                "file": fp,
                "hits": hits[:10],
                "snippet": code[:2000],
            }
            schema_hint = {"risks": [{"title": "string", "severity": "low|medium|high|critical", "mitigation": "string"}]}
            tracer.emit("security.llm.request", {"file": fp, "model": model})
            resp = ollama_chat_json(
                model=model,
                system=SYSTEM_PROMPT,
                user=f"Given the scan hits and snippet, refine risk explanation and mitigations.\n\n{user}",
                schema_hint=schema_hint,
                temperature=0.2,
            )
            valid_resp = safe_validate(SecurityResponseModel, resp)
            if not valid_resp:
                tracer.emit("security.llm.response.error", {"file": fp, "response": resp}, level="ERROR", span_id=span_id, parent_span_id=parent_span_id)
                tracer.emit_metric("security.llm.validation_error.count")
                continue
            tracer.emit("security.llm.response", {"file": fp, "risks": len(valid_resp.risks)}, span_id=span_id, parent_span_id=parent_span_id)
            tracer.emit_metric("security.llm.calls.count")
            for r in valid_resp.risks:
                findings.append(
                    {
                        "file": fp,
                        "type": "security",
                        "severity": r.severity,
                        "title": r.title or "Security improvement",
                        "details": "LLM refinement based on local scan hits.",
                        "recommendation": r.mitigation or "",
                        "evidence": {"source": "llm_enrichment"},
                    }
                )

    state["security_findings"] = findings
    tracer.emit_metric("security.findings.total", float(len(findings)))
    tracer.end_span("security", span_id=span_id, parent_span_id=parent_span_id, payload={"findings": len(findings)})
    return state


def _recommendation_for_rule(rule_id: str | None) -> str:
    match rule_id:
        case "SEC001":
            return "Move secrets to environment variables or a secret manager; rotate exposed credentials."
        case "SEC002":
            return "Use parameterized queries / prepared statements; never concatenate user input into SQL strings."
        case "SEC003":
            return "Avoid eval/exec; use safe parsers or explicit dispatch tables."
        case "SEC004":
            return "Avoid untrusted pickle deserialization; use JSON or a safe serialization format."
        case "SEC005":
            return "Avoid shell=True; pass argv arrays and validate/sanitize inputs."
        case _:
            return "Review the code path and apply secure coding best practices."


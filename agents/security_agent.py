from __future__ import annotations

from agents.state_types import FindingDict, ReviewStateDict
from observability.tracer import JsonlTracer
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
    tracer = JsonlTracer(state["run_dir"])
    tracer.emit("security.start", {"files": len(state.get("project_files", []))})

    model = state["model"]
    findings: list[FindingDict] = []

    for fp, code in state.get("file_contents", {}).items():
        hits = scan_security_risks(code)
        tracer.emit("tool.scan_security_risks", {"file": fp, "hits": hits})

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
            tracer.emit("security.llm.response", {"file": fp, "response": resp})
            for r in (resp.get("risks") or []) if isinstance(resp, dict) else []:
                findings.append(
                    {
                        "file": fp,
                        "type": "security",
                        "severity": (r.get("severity") or "low"),
                        "title": r.get("title") or "Security improvement",
                        "details": "LLM refinement based on local scan hits.",
                        "recommendation": r.get("mitigation") or "",
                        "evidence": {"source": "llm_enrichment"},
                    }
                )

    state["security_findings"] = findings
    tracer.emit("security.done", {"findings": len(findings)})
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


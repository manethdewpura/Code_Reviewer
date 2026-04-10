from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from agents.state_types import ReviewStateDict
from observability.tracer import JsonlTracer


def report_generator_agent(state: ReviewStateDict) -> ReviewStateDict:
    tracer = JsonlTracer(state["run_dir"])
    tracer.emit("report.start", {})

    q = state.get("quality_findings", [])
    s = state.get("security_findings", [])
    r = state.get("refactor_findings", [])

    sev_counts = Counter([f.get("severity", "low") for f in (q + s + r)])
    type_counts = Counter([f.get("type", "unknown") for f in (q + s + r)])

    final: dict[str, Any] = {
        "meta": {
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "project_root": state.get("project_root"),
            "model": state.get("model"),
            "files_analyzed": len(state.get("project_files", [])),
        },
        "summary": {
            "total_findings": len(q) + len(s) + len(r),
            "by_severity": dict(sev_counts),
            "by_type": dict(type_counts),
        },
        "quality_findings": q,
        "security_findings": s,
        "refactor_suggestions": r,
    }

    state["final_report"] = final
    tracer.emit("report.done", {"total_findings": final["summary"]["total_findings"]})
    return state


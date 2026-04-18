from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from agents.state_types import ReviewStateDict
from observability.tracer import JsonlTracer
from tools.file_reader import list_project_files, read_code_file


def coordinator_agent(state: ReviewStateDict) -> ReviewStateDict:
    """Coordinator: ingest project, read files, initialize state + run trace."""
    project_root = state["project_root"]
    run_id = state.get("run_id") or str(uuid4())
    state["run_id"] = run_id
    run_dir = state.get("run_dir")
    if not run_dir:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = str((Path(__file__).resolve().parents[1] / "runs" / ts).resolve())
        state["run_dir"] = run_dir

    tracer = JsonlTracer(run_dir, run_id=run_id, component="coordinator")
    span_id = tracer.start_span("coordinator", payload={"project_root": project_root, "model": state.get("model")})
    state["active_span_id"] = span_id

    files = list_project_files(project_root)
    contents: dict[str, str] = {}
    for fp in files:
        try:
            contents[fp] = read_code_file(fp)
        except Exception as e:
            tracer.emit("tool.read_code_file.error", {"file": fp, "error": str(e)}, level="ERROR", span_id=span_id)
            tracer.emit_metric("tool.read_code_file.error.count")

    state["project_files"] = files
    state["file_contents"] = contents
    state["execution_plan"] = {
        "run_quality": bool(contents),
        "run_security": bool(contents),
        "run_refactor": bool(contents),
    }
    state.setdefault("security_mode", "normal")
    state.setdefault("security_escalation_done", False)
    state.setdefault("quality_findings", [])
    state.setdefault("security_findings", [])
    state.setdefault("refactor_findings", [])
    state.setdefault("final_report", {})

    tracer.emit_metric("coordinator.files_total", float(len(files)))
    tracer.emit_metric("coordinator.files_read", float(len(contents)))
    tracer.end_span(
        "coordinator",
        span_id=span_id,
        payload={"files_total": len(files), "files_read": len(contents)},
    )
    return state
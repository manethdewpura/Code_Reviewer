from __future__ import annotations

from datetime import datetime
from pathlib import Path

from agents.state_types import ReviewStateDict
from observability.tracer import JsonlTracer
from tools.file_reader import list_project_files, read_code_file


def coordinator_agent(state: ReviewStateDict) -> ReviewStateDict:
    """Coordinator: ingest project, read files, initialize state + run trace."""
    project_root = state["project_root"]
    run_dir = state.get("run_dir")
    if not run_dir:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = str((Path(__file__).resolve().parents[1] / "runs" / ts).resolve())
        state["run_dir"] = run_dir

    tracer = JsonlTracer(run_dir)
    tracer.emit("coordinator.start", {"project_root": project_root, "model": state.get("model")})

    files = list_project_files(project_root)
    contents: dict[str, str] = {}
    for fp in files:
        try:
            contents[fp] = read_code_file(fp)
        except Exception as e:
            tracer.emit("tool.read_code_file.error", {"file": fp, "error": str(e)})

    state["project_files"] = files
    state["file_contents"] = contents
    state.setdefault("quality_findings", [])
    state.setdefault("security_findings", [])
    state.setdefault("refactor_findings", [])
    state.setdefault("final_report", {})

    tracer.emit(
        "coordinator.done",
        {"files_total": len(files), "files_read": len(contents)},
    )
    return state


from __future__ import annotations

import argparse
import json
from pathlib import Path

from langgraph.graph import END, StateGraph

from agents.code_quality_agent import code_quality_agent
from agents.coordinator import coordinator_agent
from agents.refactor_agent import refactor_agent
from agents.security_agent import security_agent
from agents.state_types import ReviewStateDict
from reporting.report_generator import report_generator_agent


def _route_from_coordinator(state: ReviewStateDict) -> str:
    plan = state.get("execution_plan", {})
    if plan.get("run_quality"):
        return "quality"
    if plan.get("run_security"):
        return "security"
    if plan.get("run_refactor"):
        return "refactor"
    return "report"


def _route_after_quality(state: ReviewStateDict) -> str:
    plan = state.get("execution_plan", {})
    if plan.get("run_security"):
        return "security"
    if plan.get("run_refactor") and state.get("quality_findings"):
        return "refactor"
    return "report"


def _route_after_security(state: ReviewStateDict) -> str:
    plan = state.get("execution_plan", {})
    has_actionable_findings = bool(state.get("quality_findings") or state.get("security_findings"))
    if plan.get("run_refactor") and has_actionable_findings:
        return "refactor"
    return "report"


def build_graph() -> StateGraph:
    graph = StateGraph(ReviewStateDict)
    graph.add_node("coordinator", coordinator_agent)
    graph.add_node("quality", code_quality_agent)
    graph.add_node("security", security_agent)
    graph.add_node("refactor", refactor_agent)
    graph.add_node("report", report_generator_agent)

    graph.set_entry_point("coordinator")
    graph.add_conditional_edges(
        "coordinator",
        _route_from_coordinator,
        {
            "quality": "quality",
            "security": "security",
            "refactor": "refactor",
            "report": "report",
        },
    )
    graph.add_conditional_edges(
        "quality",
        _route_after_quality,
        {"security": "security", "refactor": "refactor", "report": "report"},
    )
    graph.add_conditional_edges(
        "security",
        _route_after_security,
        {"refactor": "refactor", "report": "report"},
    )
    graph.add_edge("refactor", "report")
    graph.add_edge("report", END)
    return graph


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Offline Multi-Agent Code Reviewer (Ollama + LangGraph)")
    p.add_argument("--project", required=True, help="Path to the project folder to analyze")
    p.add_argument("--model", default="llama3.1:8b", help="Ollama model name (must be local)")
    p.add_argument("--out", default="report.json", help="Output JSON path")
    return p.parse_args()


def resolve_out_path(out_arg: str) -> Path:
    """
    If `--out` is a bare filename (e.g. "report.json"), write under `reports/`.
    If it includes a directory component (e.g. "reports/foo.json" or "out/foo.json")
    or is absolute, respect it as provided.
    """
    p = Path(out_arg).expanduser()
    if p.is_absolute():
        return p.resolve()
    if p.parent != Path("."):
        return p.resolve()
    return (Path("reports") / p.name).resolve()


def run_review(*, project_root: str, model: str) -> ReviewStateDict:
    """Execute the full multi-agent review graph and return final state."""
    initial: ReviewStateDict = {
        "project_root": str(Path(project_root).expanduser().resolve()),
        "model": model,
    }
    app = build_graph().compile()
    return app.invoke(initial)


def main() -> None:
    args = parse_args()
    project_root = str(Path(args.project).expanduser().resolve())
    out_path = resolve_out_path(args.out)
    final_state = run_review(project_root=project_root, model=args.model)

    report = final_state.get("final_report", {})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    run_dir = final_state.get("run_dir")
    print(f"Wrote report to: {out_path}")
    if run_dir:
        print(f"Run trace saved under: {run_dir}")


if __name__ == "__main__":
    main()


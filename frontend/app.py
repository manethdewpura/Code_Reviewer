from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

import streamlit as st

# Ensure repo-root imports work when launching via `streamlit run frontend/app.py`.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import resolve_out_path, run_review
from agents.code_quality_agent import code_quality_agent
from agents.coordinator import coordinator_agent
from agents.refactor_agent import refactor_agent
from agents.security_agent import security_agent
from reporting.report_generator import report_generator_agent


st.set_page_config(page_title="MAS Code Reviewer", page_icon=":mag:", layout="wide")

st.title("MAS Code Reviewer")
st.caption("Offline multi-agent code review UI (LangGraph + Ollama)")


def _pick_folder_dialog(initial_dir: str) -> str | None:
    """Open a local folder picker dialog and return selected path."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(initialdir=initial_dir or str(Path.home()))
    finally:
        root.destroy()
    return selected or None


with st.sidebar:
    st.header("Run Settings")
    default_project = str(Path(".").resolve())
    if "project_root" not in st.session_state:
        st.session_state["project_root"] = default_project

    project_root_input = st.text_input(
        "Project path",
        value=str(st.session_state["project_root"]),
        help="Target folder to analyze.",
    )
    st.session_state["project_root"] = project_root_input

    if st.button("Browse Folder", use_container_width=True):
        picked = _pick_folder_dialog(str(st.session_state["project_root"]))
        if picked:
            st.session_state["project_root"] = picked
            st.rerun()
        else:
            st.warning("Folder picker unavailable or no folder selected.")

    project_root = str(st.session_state["project_root"])
    model = st.text_input("Ollama model", value="llama3.1:8b")
    out_name = st.text_input("Output filename", value="report.json", help="Bare filename saves to reports/.")
    run_button = st.button("Run Analysis", type="primary", use_container_width=True)


def _show_findings(title: str, rows: list[dict[str, Any]]) -> None:
    st.subheader(title)
    if not rows:
        st.info("No items.")
        return
    st.dataframe(
        [
            {
                "file": r.get("file"),
                "severity": r.get("severity"),
                "title": r.get("title"),
                "recommendation": r.get("recommendation"),
            }
            for r in rows
        ],
        use_container_width=True,
        hide_index=True,
    )


def _show_agent_workflow() -> None:
    st.subheader("How Each Agent Works")
    st.markdown(
        "Coordinator -> (Quality?) -> (Security?) -> (Security Escalation on critical?) -> (Refactor?) -> Report"
    )
    st.caption("Conditional LangGraph handoff through shared state with one-step security escalation.")

    with st.expander("1) Coordinator Agent", expanded=False):
        st.markdown(
            "- **Input**: `project_root`, `model`\n"
            "- **Tools**: `list_project_files`, `read_code_file`\n"
            "- **Output to state**: `project_files`, `file_contents`, `run_dir`\n"
            "- **Trace events**: `coordinator.start`, `coordinator.done`"
        )
    with st.expander("2) Code Quality Agent", expanded=False):
        st.markdown(
            "- **Input**: loaded file contents\n"
            "- **Tools**: `calculate_complexity` (+ optional Ollama JSON enrichment)\n"
            "- **Output to state**: `quality_findings`\n"
            "- **Trace events**: `quality.start`, `tool.calculate_complexity`, `quality.llm.*`, `quality.done`"
        )
    with st.expander("3) Security Agent", expanded=False):
        st.markdown(
            "- **Input**: loaded file contents\n"
            "- **Tools**: `scan_security_risks` (+ optional Ollama JSON enrichment)\n"
            "- **Output to state**: `security_findings`\n"
            "- **Trace events**: `security.start`, `tool.scan_security_risks`, `security.llm.*`, `security.done`"
        )
    with st.expander("4) Security Escalation (conditional)", expanded=False):
        st.markdown(
            "- **Trigger**: one or more `critical` security findings\n"
            "- **Goal**: run one additional security pass for higher confidence\n"
            "- **Safety**: single escalation only (`security_escalation_done`)\n"
            "- **Trace events**: same `security.*` events, with component `security_escalation`"
        )
    with st.expander("5) Refactor Agent", expanded=False):
        st.markdown(
            "- **Input**: quality + security findings\n"
            "- **Tools**: `generate_refactor_suggestions` + Ollama planner\n"
            "- **Output to state**: `refactor_findings`\n"
            "- **Trace events**: `refactor.start`, `tool.generate_refactor_suggestions`, `refactor.llm.*`, `refactor.done`"
        )
    with st.expander("6) Report Agent", expanded=False):
        st.markdown(
            "- **Input**: all findings from prior agents\n"
            "- **Tools**: summary aggregation + tracer\n"
            "- **Output**: `final_report` JSON\n"
            "- **Trace events**: `report.start`, `report.done`"
        )


def _show_trace_preview(run_dir: str | None) -> None:
    st.subheader("Execution Trace Preview")
    if not run_dir:
        st.info("Run an analysis to view trace events.")
        return

    trace_path = Path(run_dir) / "trace.jsonl"
    if not trace_path.exists():
        st.warning(f"Trace file not found: {trace_path}")
        return

    try:
        lines = trace_path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        st.warning(f"Could not read trace: {exc}")
        return

    if not lines:
        st.info("Trace file is empty.")
        return

    events: list[dict[str, Any]] = []
    for line in lines[-25:]:
        try:
            rec = json.loads(line)
            events.append(
                {
                    "ts": rec.get("ts"),
                    "level": rec.get("level", "INFO"),
                    "component": rec.get("component"),
                    "event": rec.get("event"),
                    "payload": rec.get("payload"),
                }
            )
        except Exception:
            continue

    if not events:
        st.info("No parseable events in trace.")
        return

    st.dataframe(events, use_container_width=True, hide_index=True)


def _compact_payload(payload: Any, *, max_len: int = 160) -> str:
    if payload is None:
        return ""
    try:
        text = json.dumps(payload, ensure_ascii=False)
    except Exception:
        text = str(payload)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _render_cursor_style_live_logs(container: Any, log_rows: list[dict[str, Any]]) -> None:
    """Render a Cursor-like live activity panel with compact status cards."""
    if not log_rows:
        container.info("Waiting for agent activity...")
        return

    latest_by_agent: dict[str, dict[str, Any]] = {}
    for row in log_rows:
        agent = str(row.get("agent", "Unknown"))
        latest_by_agent[agent] = row

    ordered_agents = [
        "Coordinator",
        "Code Quality",
        "Security",
        "Security Escalation",
        "Refactor",
        "Report",
    ]

    cards = container.container()
    cols = cards.columns(3)
    for i, agent in enumerate(ordered_agents):
        info = latest_by_agent.get(agent)
        if not info:
            cols[i % 3].markdown(f"**{agent}**\n\n`idle`")
            continue
        status = str(info.get("status", "unknown"))
        icon = "🟢" if status == "done" else "🟡" if status == "running" else "⚪"
        elapsed = info.get("elapsed_ms")
        elapsed_txt = f" · `{elapsed} ms`" if elapsed is not None else ""
        details = str(info.get("details", ""))
        cols[i % 3].markdown(
            f"**{icon} {agent}**\n\n`{status}`{elapsed_txt}\n\n{details}"
        )

    stream_lines: list[str] = []
    for row in log_rows[-14:]:
        agent = str(row.get("agent", "Unknown"))
        status = str(row.get("status", "unknown"))
        details = str(row.get("details", ""))
        marker = ">" if status == "running" else "-"
        stream_lines.append(f"{marker} {agent}: {status} | {details}")
    container.code("\n".join(stream_lines), language="text")


def _show_background_activity(run_dir: str | None) -> None:
    st.subheader("Background Agent Activity")
    if not run_dir:
        st.info("Run an analysis to inspect background agent behavior.")
        return

    trace_path = Path(run_dir) / "trace.jsonl"
    if not trace_path.exists():
        st.warning(f"Trace file not found: {trace_path}")
        return

    try:
        lines = trace_path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        st.warning(f"Could not read trace: {exc}")
        return

    records: list[dict[str, Any]] = []
    for line in lines:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        records.append(rec)

    if not records:
        st.info("No parseable events in trace.")
        return

    components = sorted({str(r.get("component") or "unknown") for r in records})
    selected_components = st.multiselect(
        "Filter components",
        options=components,
        default=components,
        help="Choose which agents/components to display in the timeline.",
    )
    show_tool_events = st.checkbox("Show tool-level events", value=True)
    show_llm_events = st.checkbox("Show LLM events", value=True)

    timeline: list[dict[str, Any]] = []
    for rec in records:
        component = str(rec.get("component") or "unknown")
        event = str(rec.get("event") or "")
        if component not in selected_components:
            continue
        if not show_tool_events and event.startswith("tool."):
            continue
        if not show_llm_events and ".llm." in event:
            continue
        timeline.append(
            {
                "ts": rec.get("ts"),
                "level": rec.get("level", "INFO"),
                "component": component,
                "event": event,
                "span_id": rec.get("span_id"),
                "parent_span_id": rec.get("parent_span_id"),
                "what_happened": _compact_payload(rec.get("payload")),
            }
        )

    if not timeline:
        st.info("No events matched the current filters.")
    else:
        st.dataframe(timeline[-250:], use_container_width=True, hide_index=True)

    metrics_path = Path(run_dir) / "metrics.json"
    if metrics_path.exists():
        try:
            metrics_doc = json.loads(metrics_path.read_text(encoding="utf-8"))
            counters = metrics_doc.get("counters", {})
            if isinstance(counters, dict) and counters:
                st.caption("Aggregated counters (from metrics.json)")
                metric_rows = [
                    {"metric": k, "value": v}
                    for k, v in sorted(counters.items(), key=lambda kv: kv[0])
                ]
                st.dataframe(metric_rows, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.warning(f"Could not read metrics: {exc}")


def _live_step_summary(step_name: str, state: dict[str, Any]) -> str:
    if step_name == "Coordinator":
        return (
            f"files discovered: {len(state.get('project_files', []))}, "
            f"files loaded: {len(state.get('file_contents', {}))}"
        )
    if step_name == "Code Quality":
        return f"quality findings: {len(state.get('quality_findings', []))}"
    if step_name == "Security":
        return f"security findings: {len(state.get('security_findings', []))}"
    if step_name == "Refactor":
        return f"refactor suggestions: {len(state.get('refactor_findings', []))}"
    if step_name == "Report":
        summary = state.get("final_report", {}).get("summary", {})
        return f"total findings: {summary.get('total_findings', 0)}"
    return "step completed"


def _run_review_live(
    project_root: str,
    model: str,
    on_update: Callable[[list[dict[str, Any]]], None] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run agent pipeline step-by-step for live UI updates."""
    state: dict[str, Any] = {"project_root": project_root, "model": model}
    steps = [
        ("Coordinator", coordinator_agent),
        ("Code Quality", code_quality_agent),
        ("Security", security_agent),
    ]

    logs: list[dict[str, Any]] = []
    for step_name, step_fn in steps:
        started = perf_counter()
        logs.append({"agent": step_name, "status": "running", "details": "started"})
        if on_update:
            on_update(logs)
        state = step_fn(state)
        elapsed_ms = int((perf_counter() - started) * 1000)
        logs.append(
            {
                "agent": step_name,
                "status": "done",
                "details": _live_step_summary(step_name, state),
                "elapsed_ms": elapsed_ms,
            }
        )
        if on_update:
            on_update(logs)

    has_critical = any(f.get("severity") == "critical" for f in state.get("security_findings", []))
    if has_critical and not state.get("security_escalation_done", False):
        started = perf_counter()
        logs.append({"agent": "Security Escalation", "status": "running", "details": "critical finding triggered escalation"})
        if on_update:
            on_update(logs)
        from agents.security_agent import security_escalation_agent

        state = security_escalation_agent(state)
        elapsed_ms = int((perf_counter() - started) * 1000)
        logs.append(
            {
                "agent": "Security Escalation",
                "status": "done",
                "details": f"security findings: {len(state.get('security_findings', []))}",
                "elapsed_ms": elapsed_ms,
            }
        )
        if on_update:
            on_update(logs)

    followup_steps = [
        ("Refactor", refactor_agent),
        ("Report", report_generator_agent),
    ]
    for step_name, step_fn in followup_steps:
        started = perf_counter()
        logs.append({"agent": step_name, "status": "running", "details": "started"})
        if on_update:
            on_update(logs)
        state = step_fn(state)
        elapsed_ms = int((perf_counter() - started) * 1000)
        logs.append(
            {
                "agent": step_name,
                "status": "done",
                "details": _live_step_summary(step_name, state),
                "elapsed_ms": elapsed_ms,
            }
        )
        if on_update:
            on_update(logs)
    return state, logs


_show_agent_workflow()

if "last_run_dir" not in st.session_state:
    st.session_state["last_run_dir"] = None

if run_button:
    target = Path(project_root).expanduser()
    if not target.exists() or not target.is_dir():
        st.error(f"Invalid project path: {target}")
    else:
        live_panel = st.container(border=True)
        live_panel.subheader("Live Agent Activity")
        live_log_placeholder = live_panel.empty()

        with st.spinner("Running multi-agent review..."):
            try:
                def _push_live(log_rows: list[dict[str, Any]]) -> None:
                    with live_log_placeholder.container():
                        _render_cursor_style_live_logs(live_log_placeholder, log_rows)

                final_state, live_logs = _run_review_live(
                    project_root=str(target),
                    model=model,
                    on_update=_push_live,
                )
                report = final_state.get("final_report", {})

                out_path = resolve_out_path(out_name)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

                st.success(f"Report written to: {out_path}")
                run_dir = final_state.get("run_dir")
                st.session_state["last_run_dir"] = run_dir
                if run_dir:
                    st.caption(f"Trace: {run_dir}")

                meta = report.get("meta", {})
                summary = report.get("summary", {})
                c1, c2, c3 = st.columns(3)
                c1.metric("Files analyzed", meta.get("files_analyzed", 0))
                c2.metric("Total findings", summary.get("total_findings", 0))
                c3.metric("Model", str(meta.get("model", model)))

                st.subheader("Summary")
                st.json(summary)

                _show_findings("Quality Findings", report.get("quality_findings", []))
                _show_findings("Security Findings", report.get("security_findings", []))
                _show_findings("Refactor Suggestions", report.get("refactor_suggestions", []))

                report_text = json.dumps(report, indent=2, ensure_ascii=False)
                st.download_button(
                    "Download Report JSON",
                    data=report_text,
                    file_name=out_path.name,
                    mime="application/json",
                    use_container_width=True,
                )
            except Exception as exc:
                st.exception(exc)

_show_trace_preview(st.session_state.get("last_run_dir"))
_show_background_activity(st.session_state.get("last_run_dir"))


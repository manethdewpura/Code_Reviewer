from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import main as app_main
from tools.ollama_client import ollama_chat_json


JUDGE_SYSTEM = """
You are an automated evaluator (LLM-as-a-judge) for a multi-agent code review system.

You will receive the produced JSON report. Your job is to judge whether it is:
- well-formed JSON
- contains the required keys
- contains non-empty and relevant content for the analyzed project

Return JSON only. Be strict and deterministic.
""".strip()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Local LLM-as-a-judge evaluation (Ollama only).")
    p.add_argument("--project", required=True, help="Path to project folder to analyze")
    p.add_argument("--model", default="llama3.1:8b", help="Ollama model used by agents")
    p.add_argument("--judge-model", default="", help="Ollama model for judge (defaults to --model)")
    p.add_argument("--out", default="judge_result.json", help="Where to write the judge result JSON")
    return p.parse_args()


def judge_report(*, judge_model: str, report: dict[str, Any]) -> dict[str, Any]:
    schema_hint = {
        "pass": "boolean",
        "score": "number (0-10)",
        "checks": {
            "has_meta": "boolean",
            "has_summary": "boolean",
            "has_findings_arrays": "boolean",
            "evidence_of_tooling": "boolean",
        },
        "notes": ["string"],
    }

    resp = ollama_chat_json(
        model=judge_model,
        system=JUDGE_SYSTEM,
        user=(
            "Evaluate this report object.\n"
            "Required top-level keys: meta, summary, quality_findings, security_findings, refactor_suggestions.\n\n"
            f"{json.dumps(report, ensure_ascii=False)[:12000]}"
        ),
        schema_hint=schema_hint,
        temperature=0.0,
    )
    if not isinstance(resp, dict):
        return {"pass": False, "score": 0, "notes": ["Judge did not return a JSON object."]}
    return resp


def main() -> None:
    args = _parse_args()
    project_root = str(Path(args.project).expanduser().resolve())
    model = args.model
    judge_model = args.judge_model or model

    graph = app_main.build_graph().compile()
    final_state = graph.invoke({"project_root": project_root, "model": model})
    report = final_state.get("final_report", {})

    result = judge_report(judge_model=judge_model, report=report)
    result.setdefault("meta", {})
    result["meta"].update(
        {
            "project_root": project_root,
            "model": model,
            "judge_model": judge_model,
            "run_dir": final_state.get("run_dir"),
        }
    )

    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote judge result to: {out_path}")
    if os.getenv("CI"):
        # In CI, make it easy to spot accidental execution.
        print("Note: judge is intended for local execution with Ollama.")


if __name__ == "__main__":
    main()


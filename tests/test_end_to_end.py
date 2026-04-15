from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import main as app_main


def _fake_ollama_chat_json(**_: Any) -> dict[str, Any]:
    # Minimal valid structures for agents that expect these keys
    return {"issues": [], "risks": [], "plan": []}


def test_graph_runs_without_ollama(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Patch all LLM calls to keep tests offline and deterministic
    monkeypatch.setattr("agents.code_quality_agent.ollama_chat_json", _fake_ollama_chat_json)
    monkeypatch.setattr("agents.security_agent.ollama_chat_json", _fake_ollama_chat_json)
    monkeypatch.setattr("agents.refactor_agent.ollama_chat_json", _fake_ollama_chat_json)

    # Create a tiny project
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def add(a,b):\n    return a+b\n", encoding="utf-8")
    (proj / "b.py").write_text("password='1234'\n", encoding="utf-8")

    graph = app_main.build_graph().compile()
    final_state = graph.invoke({"project_root": str(proj), "model": "dummy"})

    report = final_state.get("final_report")
    assert report and report["meta"]["files_analyzed"] == 2
    assert "security_findings" in report

    # Ensure JSON serializable
    json.dumps(report)


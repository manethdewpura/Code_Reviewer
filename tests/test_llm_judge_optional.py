from __future__ import annotations

import json
import os
from typing import Any

import pytest

import main as app_main
from tools.ollama_client import ollama_chat_json


def _ollama_available() -> bool:
    try:
        import ollama  # noqa: F401

        # `ollama` package can be installed but server may be down.
        # A small, fast call: list models.
        import ollama as _ollama

        _ollama.list()
        return True
    except Exception:
        return False


@pytest.mark.skipif(os.getenv("OLLAMA_EVAL") != "1", reason="Set OLLAMA_EVAL=1 to run local judge evaluation.")
@pytest.mark.skipif(not _ollama_available(), reason="Ollama server not available.")
def test_report_passes_local_llm_judge() -> None:
    """
    Optional 'LLM-as-a-judge' evaluation (local-only).
    This is skipped by default to keep the test suite deterministic and zero-dependency on a running Ollama daemon.
    """
    graph = app_main.build_graph().compile()
    final_state = graph.invoke({"project_root": os.getcwd(), "model": os.getenv("OLLAMA_MODEL", "llama3.1:8b")})
    report = final_state.get("final_report", {})

    schema_hint = {
        "pass": "boolean",
        "score": "number (0-10)",
        "notes": ["string"],
    }
    judge: dict[str, Any] = ollama_chat_json(
        model=os.getenv("OLLAMA_JUDGE_MODEL", os.getenv("OLLAMA_MODEL", "llama3.1:8b")),
        system="You are a strict evaluator. Return JSON only.",
        user=(
            "Does this report include top-level keys meta, summary, quality_findings, security_findings, refactor_suggestions "
            "and does it look consistent?\n\n"
            + json.dumps(report, ensure_ascii=False)[:12000]
        ),
        schema_hint=schema_hint,
        temperature=0.0,
    )

    assert isinstance(judge, dict)
    assert judge.get("pass") in {True, False}
    # If judge can't parse, our client returns {"_parse_error": True, ...}
    assert judge.get("_parse_error") is not True


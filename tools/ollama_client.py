from __future__ import annotations

import json
from typing import Any

import ollama


def ollama_chat_json(
    *,
    model: str,
    system: str,
    user: str,
    schema_hint: dict[str, Any] | None = None,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Call a local Ollama chat model and attempt to parse JSON output.

    The prompts enforce JSON-only output. If parsing fails, returns a best-effort wrapper.
    """
    schema_text = ""
    if schema_hint:
        schema_text = "\n\nReturn JSON matching this schema hint:\n" + json.dumps(schema_hint, indent=2)

    resp = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": system.strip() + schema_text},
            {
                "role": "user",
                "content": user.strip()
                + "\n\nOutput MUST be valid JSON only (no markdown, no backticks).",
            },
        ],
        options={"temperature": temperature},
    )
    content = (resp.get("message", {}) or {}).get("content", "")
    try:
        return json.loads(content)
    except Exception:
        return {"_parse_error": True, "raw": content}


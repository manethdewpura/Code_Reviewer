from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any


def _jsonable(x: Any) -> Any:
    if is_dataclass(x):
        return asdict(x)
    if isinstance(x, Path):
        return str(x)
    return x


class JsonlTracer:
    """Simple local tracing for AgentOps/observability.

    Writes one JSON object per line with timestamps.
    """

    def __init__(self, run_dir: str, *, run_id: str | None = None, component: str | None = None) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / "trace.jsonl"
        self.metrics_path = self.run_dir / "metrics.json"
        self.run_id = run_id or "unknown"
        self.component = component or "unknown"

    def emit(
        self,
        event: str,
        payload: dict[str, Any],
        *,
        level: str = "INFO",
        span_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event,
            "level": level,
            "run_id": self.run_id,
            "component": self.component,
            "event_id": str(uuid4()),
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=_jsonable, ensure_ascii=False) + os.linesep)

    def start_span(self, name: str, *, parent_span_id: str | None = None, payload: dict[str, Any] | None = None) -> str:
        span_id = str(uuid4())
        self.emit(
            f"{name}.start",
            payload or {},
            span_id=span_id,
            parent_span_id=parent_span_id,
        )
        return span_id

    def end_span(
        self,
        name: str,
        *,
        span_id: str,
        parent_span_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.emit(
            f"{name}.done",
            payload or {},
            span_id=span_id,
            parent_span_id=parent_span_id,
        )

    def emit_metric(
        self,
        name: str,
        value: float = 1.0,
        *,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        key = name if not tags else f"{name}|" + "|".join(f"{k}={v}" for k, v in sorted(tags.items()))
        doc: dict[str, Any] = {"run_id": self.run_id, "counters": {}}
        if self.metrics_path.exists():
            try:
                doc = json.loads(self.metrics_path.read_text(encoding="utf-8"))
            except Exception:
                doc = {"run_id": self.run_id, "counters": {}}
        counters = doc.setdefault("counters", {})
        counters[key] = float(counters.get(key, 0.0)) + value
        self.metrics_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


"""Low-overhead per-run token and tool-result telemetry."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from typing import Any

from .artifacts import artifact_disk_path

_LOCK = threading.Lock()
_LEDGER_PATH = "/metrics/token_usage.jsonl"


def _append(row: dict[str, Any]) -> None:
    path = artifact_disk_path(_LEDGER_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str)
    with _LOCK, path.open("a", encoding="utf-8") as handle:
        handle.write(encoded + "\n")


def record_model_usage(
    *,
    agent: str,
    call_id: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Record one incremental provider-usage observation."""
    _append(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "kind": "model_usage",
            "agent": agent,
            "call_id": call_id,
            "input_tokens": max(0, input_tokens),
            "output_tokens": max(0, output_tokens),
        }
    )


def record_tool_result(*, agent: str, tool: str | None, call_id: str, content: Any) -> None:
    """Record only tool-result size and envelope metadata, never evidence text."""
    rendered = content if isinstance(content, str) else json.dumps(content, default=str)
    result_id = None
    cache_status = None
    try:
        parsed = json.loads(rendered)
        if isinstance(parsed, dict):
            result_id = parsed.get("result_id")
            freshness = parsed.get("freshness")
            if isinstance(freshness, dict):
                cache_status = freshness.get("cache")
    except (TypeError, json.JSONDecodeError):
        pass
    _append(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "kind": "tool_result",
            "agent": agent,
            "tool": tool,
            "call_id": call_id,
            "characters": len(rendered),
            "approx_tokens": (len(rendered) + 3) // 4,
            "result_id": result_id,
            "cache": cache_status,
        }
    )

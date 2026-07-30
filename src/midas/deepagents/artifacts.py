"""Content-addressed storage and compact response envelopes for research tools."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .workspace import agent_output_directory

ARTIFACT_SCHEMA_VERSION = 1
DEFAULT_INLINE_CHAR_LIMIT = 8_000
BATCH_INLINE_CHAR_LIMIT = 24_000


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def artifact_disk_path(virtual_path: str) -> Path:
    """Resolve a virtual agent path inside the active physical workspace."""
    return (agent_output_directory() / virtual_path.lstrip("/")).resolve()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass


def _clip_string(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    suffix = f"… [{len(value) - limit:,} characters in artifact]"
    return value[: max(0, limit - len(suffix))].rstrip() + suffix


def _compact_value(value: Any, *, string_limit: int = 1_200, list_limit: int = 20) -> Any:
    """Bound individual fields while preserving a useful structured preview."""
    if isinstance(value, str):
        return _clip_string(value, string_limit)
    if isinstance(value, Mapping):
        return {
            str(key): _compact_value(item, string_limit=string_limit, list_limit=list_limit)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = list(value)
        compact = [
            _compact_value(item, string_limit=string_limit, list_limit=list_limit)
            for item in items[:list_limit]
        ]
        if len(items) > list_limit:
            compact.append({"omitted_items": len(items) - list_limit})
        return compact
    return value


def _fit_summary(summary: Any, *, max_characters: int) -> Any:
    compact = _compact_value(_jsonable(summary))
    rendered = _canonical_json(compact)
    if len(rendered) <= max_characters:
        return compact

    # Tighten large leaf fields first, then fall back to a valid JSON preview.
    compact = _compact_value(compact, string_limit=320, list_limit=8)
    rendered = _canonical_json(compact)
    if len(rendered) <= max_characters:
        return compact
    return {
        "preview": _clip_string(rendered, max_characters - 120),
        "note": "Structured summary was clipped; use artifact.path for the complete result.",
    }


def write_tool_artifact(
    tool_name: str,
    payload: Any,
    *,
    summary: Any | None = None,
    sources: Sequence[Any] = (),
    fetched_at: str | None = None,
    cache_status: str = "miss",
    max_inline_characters: int = DEFAULT_INLINE_CHAR_LIMIT,
) -> str:
    """Persist a complete payload and return a bounded JSON response envelope."""
    normalized_payload = _jsonable(payload)
    artifact_document = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "tool": tool_name,
        "fetched_at": fetched_at or datetime.now(UTC).isoformat(),
        "sources": _jsonable(sources),
        "payload": normalized_payload,
    }
    canonical = _canonical_json(artifact_document)
    result_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    virtual_path = f"/tool_results/{result_id}.json"
    pretty = json.dumps(artifact_document, ensure_ascii=False, indent=2, sort_keys=True)
    disk_path = artifact_disk_path(virtual_path)
    if not disk_path.exists():
        _atomic_write(disk_path, pretty + "\n")

    inline_summary = _fit_summary(
        normalized_payload if summary is None else summary,
        max_characters=max_inline_characters,
    )
    envelope = {
        "ok": True,
        "result_id": result_id,
        "summary": inline_summary,
        "sources": _jsonable(sources),
        "artifact": {
            "path": virtual_path,
            "format": "json",
            "bytes": len(pretty.encode("utf-8")),
            "schema_version": ARTIFACT_SCHEMA_VERSION,
        },
        "freshness": {
            "fetched_at": artifact_document["fetched_at"],
            "cache": cache_status,
        },
        "truncated": len(_canonical_json(normalized_payload)) > max_inline_characters,
    }
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":"), default=str)


def artifact_payload_for_cache(response: str) -> dict[str, str]:
    """Return artifact text referenced by a successful tool response."""
    try:
        parsed = json.loads(response)
    except (TypeError, json.JSONDecodeError):
        return {}
    artifact = parsed.get("artifact") if isinstance(parsed, dict) else None
    path = artifact.get("path") if isinstance(artifact, dict) else None
    if not isinstance(path, str):
        return {}
    disk_path = artifact_disk_path(path)
    try:
        return {path: disk_path.read_text(encoding="utf-8")}
    except OSError:
        return {}


def materialize_cached_artifacts(artifacts: Mapping[str, str]) -> None:
    """Copy cached artifact documents into the current agent workspace."""
    for virtual_path, content in artifacts.items():
        if not virtual_path.startswith("/tool_results/") or not isinstance(content, str):
            continue
        target = artifact_disk_path(virtual_path)
        if not target.exists():
            _atomic_write(target, content)


def mark_cache_hit(response: str) -> str:
    """Update envelope metadata without changing the result identifier."""
    try:
        parsed = json.loads(response)
    except (TypeError, json.JSONDecodeError):
        return response
    if not isinstance(parsed, dict):
        return response
    freshness = parsed.get("freshness")
    if isinstance(freshness, dict):
        freshness["cache"] = "hit"
    parsed["reused"] = True
    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"), default=str)

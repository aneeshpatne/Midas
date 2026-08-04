"""Shared helpers for Midas DB repositories."""

from __future__ import annotations

import time
import uuid
from typing import Any


def new_id() -> str:
    return str(uuid.uuid4())


def now_ms() -> int:
    return int(time.time() * 1000)


def to_sqlite_bool(value: bool) -> int:
    return 1 if value else 0


def from_sqlite_bool(value: int | bool) -> bool:
    return bool(value)


def row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row)

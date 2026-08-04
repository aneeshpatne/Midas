"""Repository base utilities."""

from __future__ import annotations

import sqlite3
from typing import Any

from midas.db.connection import get_connection


def conn() -> sqlite3.Connection:
    return get_connection()


def fetchone_dict(cur: sqlite3.Cursor) -> dict[str, Any] | None:
    row = cur.fetchone()
    return dict(row) if row is not None else None


def fetchall_dicts(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]

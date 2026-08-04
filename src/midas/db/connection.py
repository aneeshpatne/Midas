"""SQLite connection for Midas DB (paper portfolios + research runs)."""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

# Project root: src/midas/db/connection.py -> parents[3] = repo root
_DEFAULT_DB = Path(__file__).resolve().parents[3] / "midas.db"

_local = threading.local()
_db_path: Path | None = None


def resolve_db_path(path: str | Path | None = None) -> Path:
    """Resolve DB path from argument, MIDAS_DB_PATH, or default midas.db."""
    if path is not None:
        return Path(path).expanduser().resolve()
    env = os.environ.get("MIDAS_DB_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return _DEFAULT_DB.resolve()


def configure(path: str | Path | None = None) -> Path:
    """Set the process-wide DB path and drop any thread-local connection."""
    global _db_path
    _db_path = resolve_db_path(path)
    close()
    return _db_path


def get_db_path() -> Path:
    if _db_path is None:
        configure()
    assert _db_path is not None
    return _db_path


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Open a new SQLite connection with required PRAGMAs."""
    db_file = resolve_db_path(path) if path is not None else get_db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def get_connection() -> sqlite3.Connection:
    """Thread-local shared connection for the configured DB path."""
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is None:
        conn = connect()
        _local.conn = conn
    return conn


def close() -> None:
    """Close the thread-local connection if open."""
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None

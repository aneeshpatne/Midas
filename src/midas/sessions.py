"""Durable SQLite storage for TUI agent sessions."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .deepagents.modes import (
    DEFAULT_RESEARCH_MODE,
    ResearchMode,
    normalize_research_mode,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class Session:
    session_id: str
    created_at: str
    updated_at: str
    title: str
    conversation: list[tuple[str, str]]
    mode: ResearchMode
    input_tokens: int
    output_tokens: int


class SessionStore:
    """Small SQLite repository used at TUI interaction boundaries."""

    def __init__(self, database: Path) -> None:
        self.database = database.resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    conversation TEXT NOT NULL DEFAULT '[]',
                    mode TEXT NOT NULL DEFAULT 'deep-wide',
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "mode" not in columns:
                connection.execute(
                    "ALTER TABLE sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'deep-wide'"
                )

    def create(
        self,
        session_id: str,
        *,
        mode: ResearchMode = DEFAULT_RESEARCH_MODE,
    ) -> Session:
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO sessions
                    (session_id, created_at, updated_at, mode)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, timestamp, timestamp, normalize_research_mode(mode).value),
            )
        session = self.get(session_id)
        if session is None:  # pragma: no cover
            raise RuntimeError(f"Unable to create session {session_id}")
        return session

    def save(
        self,
        session_id: str,
        conversation: list[tuple[str, str]],
        *,
        mode: ResearchMode = DEFAULT_RESEARCH_MODE,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        timestamp = _now()
        title = next(
            (text.strip().replace("\n", " ")[:80] for role, text in conversation if role == "user"),
            "",
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id, created_at, updated_at, title, conversation, mode,
                    input_tokens, output_tokens
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    title = excluded.title,
                    conversation = excluded.conversation,
                    mode = excluded.mode,
                    input_tokens = excluded.input_tokens,
                    output_tokens = excluded.output_tokens
                """,
                (
                    session_id,
                    timestamp,
                    timestamp,
                    title,
                    json.dumps(conversation, ensure_ascii=False),
                    normalize_research_mode(mode).value,
                    max(0, input_tokens),
                    max(0, output_tokens),
                ),
            )

    def get(self, session_id: str) -> Session | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def resolve(self, session_id_or_prefix: str) -> Session | None:
        value = session_id_or_prefix.strip()
        if not value:
            return None
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sessions
                WHERE session_id = ? OR session_id LIKE ?
                ORDER BY updated_at DESC
                LIMIT 2
                """,
                (value, f"{value}%"),
            ).fetchall()
        return self._from_row(rows[0]) if len(rows) == 1 else None

    def recent(self, *, exclude: str | None = None, limit: int = 10) -> list[Session]:
        query = "SELECT * FROM sessions"
        parameters: tuple[object, ...] = ()
        if exclude:
            query += " WHERE session_id != ?"
            parameters = (exclude,)
        query += " ORDER BY updated_at DESC LIMIT ?"
        parameters = (*parameters, max(1, limit))
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Session:
        raw = json.loads(row["conversation"])
        conversation = [
            (str(item[0]), str(item[1]))
            for item in raw
            if isinstance(item, list) and len(item) == 2
        ]
        return Session(
            session_id=str(row["session_id"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            title=str(row["title"]),
            conversation=conversation,
            mode=normalize_research_mode(row["mode"]),
            input_tokens=int(row["input_tokens"]),
            output_tokens=int(row["output_tokens"]),
        )

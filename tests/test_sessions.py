import sqlite3
from pathlib import Path

from midas.deepagents.modes import ResearchMode
from midas.sessions import SessionStore


def test_sqlite_session_store_round_trip_and_prefix_resolution(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "output" / ".midas-sessions.sqlite3")
    session_id = "0123456789abcdef0123456789abcdef"
    store.create(session_id)
    store.save(
        session_id,
        [("user", "NIFTY IT"), ("assistant", "Saved answer")],
        input_tokens=12,
        output_tokens=4,
    )

    restored = store.resolve("0123456789")

    assert restored is not None
    assert restored.session_id == session_id
    assert restored.title == "NIFTY IT"
    assert restored.conversation[-1] == ("assistant", "Saved answer")
    assert restored.mode == ResearchMode.DEEP_WIDE
    assert restored.input_tokens == 12
    assert restored.output_tokens == 4


def test_session_mode_round_trips(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions.sqlite3")
    session_id = "focused-session-0123456789abcdef"
    store.create(session_id, mode=ResearchMode.SINGLE_STOCK)
    store.save(
        session_id,
        [("user", "TCS")],
        mode=ResearchMode.SINGLE_STOCK,
    )

    restored = store.get(session_id)

    assert restored is not None
    assert restored.mode == ResearchMode.SINGLE_STOCK


def test_legacy_session_schema_is_migrated_to_deep_wide(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                conversation TEXT NOT NULL DEFAULT '[]',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            INSERT INTO sessions (session_id, created_at, updated_at)
            VALUES ('legacy-session', 'created', 'updated')
            """
        )

    store = SessionStore(database)
    restored = store.get("legacy-session")

    assert restored is not None
    assert restored.mode == ResearchMode.DEEP_WIDE


def test_unknown_session_mode_falls_back_to_deep_wide(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions.sqlite3")
    store.create("future-session")
    with sqlite3.connect(store.database) as connection:
        connection.execute(
            "UPDATE sessions SET mode = 'future-mode' WHERE session_id = 'future-session'"
        )

    restored = store.get("future-session")

    assert restored is not None
    assert restored.mode == ResearchMode.DEEP_WIDE

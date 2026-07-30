from pathlib import Path

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
    assert restored.input_tokens == 12
    assert restored.output_tokens == 4

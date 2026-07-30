import json
from pathlib import Path

import pytest

from midas.deepagents import cache as tool_cache
from midas.deepagents import tools
from midas.deepagents.artifacts import write_tool_artifact
from midas.deepagents.workspace import AGENT_OUTPUT_DIRECTORY


def test_tool_envelope_is_bounded_and_full_payload_is_preserved(tmp_path: Path) -> None:
    token = AGENT_OUTPUT_DIRECTORY.set(tmp_path)
    try:
        response = json.loads(
            write_tool_artifact(
                "example",
                {"rows": [{"symbol": f"S{index}", "text": "x" * 1_000} for index in range(50)]},
                max_inline_characters=2_000,
            )
        )
    finally:
        AGENT_OUTPUT_DIRECTORY.reset(token)

    assert response["ok"] is True
    assert response["truncated"] is True
    assert len(json.dumps(response["summary"])) <= 2_200
    artifact = tmp_path / response["artifact"]["path"].lstrip("/")
    stored = json.loads(artifact.read_text(encoding="utf-8"))
    assert len(stored["payload"]["rows"]) == 50
    assert stored["payload"]["rows"][-1]["text"] == "x" * 1_000


@pytest.mark.asyncio
async def test_research_batch_runs_existing_tools_sequentially(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []

    def fake_snapshot(symbol: str) -> dict:
        calls.append(symbol)
        return {
            "symbol": symbol,
            "fetched_at": "2026-07-30T00:00:00+00:00",
            "source_url": f"https://example.com/{symbol}",
            "data": {"last_price": 100},
        }

    monkeypatch.setattr("midas.deepagents.cache._get_redis_client", lambda: None)
    tool_cache._memory_cache.clear()
    monkeypatch.setattr(tools, "fetch_nse_equity_snapshot", fake_snapshot)
    token = AGENT_OUTPUT_DIRECTORY.set(tmp_path)
    try:
        response = json.loads(
            await tools.research_batch.ainvoke(
                {
                    "requests": [
                        {
                            "id": "tcs",
                            "tool": "nse_equity_snapshot",
                            "arguments": {"symbol": "TCS"},
                        },
                        {
                            "id": "infy",
                            "tool": "nse_equity_snapshot",
                            "arguments": {"symbol": "INFY"},
                        },
                    ]
                }
            )
        )
    finally:
        AGENT_OUTPUT_DIRECTORY.reset(token)

    assert calls == ["TCS", "INFY"]
    assert response["summary"]["succeeded"] == 2
    rows = response["summary"]["results"]
    assert [row["id"] for row in rows] == ["tcs", "infy"]
    assert all(row["artifact"]["path"].startswith("/tool_results/") for row in rows)

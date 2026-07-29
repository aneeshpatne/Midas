import pytest

from midas import cli
from midas.cli import run_topic


class _Message:
    def __init__(self, content: str, tool_calls: list[object] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeAgent:
    async def astream(self, payload: object, *, stream_mode: object):
        assert payload == {"messages": [("user", "Research TCS")]}
        assert stream_mode == ["updates", "custom"]
        yield "custom", {"type": "deep_agent_update", "update": "Checking primary sources."}
        yield "updates", {
            "model": {
                "messages": [
                    _Message(
                        "I will use a tool first.",
                        tool_calls=[
                            {
                                "id": "call-1",
                                "name": "company_fundamentals",
                                "args": {"symbol": "TCS"},
                            }
                        ],
                    ),
                    _Message("TCS reported steady growth."),
                ]
            }
        }


@pytest.mark.asyncio
async def test_run_topic_prints_updates_and_returns_final_answer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    answer = await run_topic("Research TCS", _FakeAgent())

    assert answer == "TCS reported steady growth."
    output = capsys.readouterr().out
    assert "[Research update]" in output


def test_main_explains_missing_deepseek_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: False)
    monkeypatch.setattr(cli.os, "getenv", lambda name: None)

    assert cli.main(["Research TCS"]) == 2
    assert "DEEPSEEK_API_KEY is not configured" in capsys.readouterr().err

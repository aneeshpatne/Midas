from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessageChunk
from textual.widgets import Input, Markdown, Static, Tree

from midas.tui.app import MidasApp
from midas.tui.events import AgentEvent, EventKind


class _FakeAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    async def astream(self, payload: Any, **kwargs: Any):
        self.calls.append((payload, kwargs))
        yield {
            "type": "messages",
            "ns": (),
            "data": (
                AIMessageChunk(content="Completed answer.", id=f"answer-{len(self.calls)}"),
                {"lc_agent_name": "midas-lead-analyst"},
            ),
        }
        yield {
            "type": "custom",
            "ns": (),
            "data": {"type": "deep_agent_update", "update": "Starting research."},
        }
        yield {
            "type": "updates",
            "ns": (),
            "data": {
                "model": {
                    "todos": [{"content": "Research universe", "status": "in_progress"}]
                }
            },
        }


class _InvalidToolHistoryAgent:
    async def astream(self, payload: Any, **kwargs: Any):
        if False:
            yield None
        raise RuntimeError(
            "insufficient tool messages following tool_calls message"
        )


@pytest.mark.asyncio
async def test_tui_submits_turn_and_reuses_context_thread(tmp_path: Path) -> None:
    fake = _FakeAgent()
    app = MidasApp(agent=fake, workspace=tmp_path)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", Input)
        prompt.value = "NIFTY IT"
        await pilot.press("enter")
        await pilot.pause(0.2)
        prompt.value = "What were the main risks?"
        await pilot.press("enter")
        await pilot.pause(0.2)

        assert len(fake.calls) == 2
        assert fake.calls[0][0]["messages"] == [("user", "NIFTY IT")]
        assert fake.calls[1][0]["messages"] == [
            ("user", "NIFTY IT"),
            ("assistant", "Completed answer."),
            ("user", "What were the main risks?"),
        ]
        assert "Research universe" in str(app.query_one("#todos", Static).render())
        assert prompt.disabled is False


@pytest.mark.asyncio
async def test_tui_tracks_and_previews_session_markdown(tmp_path: Path) -> None:
    app = MidasApp(agent=_FakeAgent(), workspace=tmp_path)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        artifact = tmp_path / "output" / "research" / "nifty-it" / "run" / "00_mandate.md"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("# Mandate\n\nBalanced horizon.", encoding="utf-8")
        app._refresh_files()
        await pilot.pause()

        tree = app.query_one("#file-tree", Tree)
        leaves = [node for node in tree.root.children[0].children[0].children if node.data]
        assert leaves[0].data == artifact.resolve()
        tree.select_node(leaves[0])
        app._preview_file(artifact)
        await pilot.pause()
        assert "Mandate" in app.query_one("#preview", Markdown).source


@pytest.mark.asyncio
async def test_new_session_changes_thread_and_clears_files(tmp_path: Path) -> None:
    app = MidasApp(agent=_FakeAgent(), workspace=tmp_path)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        old_thread = app.thread_id
        app._session_files[tmp_path / "artifact.md"] = 1
        await app._new_session()

        assert app.thread_id != old_thread
        assert app._session_files == {}
        assert app.query_one("#file-tree", Tree).root.label.plain == "output/research"


@pytest.mark.asyncio
async def test_invalid_tool_history_is_cleared_for_safe_resubmission(tmp_path: Path) -> None:
    app = MidasApp(agent=_InvalidToolHistoryAgent(), workspace=tmp_path)
    app._conversation = [("user", "old"), ("assistant", "context")]

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", Input)
        prompt.value = "Continue"
        await pilot.press("enter")
        await pilot.pause(0.2)

        assert app._conversation == []
        assert prompt.disabled is False


@pytest.mark.asyncio
async def test_raw_json_tool_results_are_not_parsed_as_rich_markup(tmp_path: Path) -> None:
    app = MidasApp(agent=_FakeAgent(), workspace=tmp_path)
    result = {
        "announcements": [
            {
                "title": "Chairman's theme \\ ITC: Partnering India\\",
                "url": "https://example.com/43f4-4f1c-99b2-9ddfff91dfdd.pdf",
            }
        ]
    }

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        transcript = app.query_one("#transcript")
        await transcript.add_activity(
            AgentEvent(
                EventKind.TOOL_FINISHED,
                "research-agent",
                result,
                "call-json",
                "nse_company_filings",
            )
        )
        await pilot.pause()

        detail = transcript.query_one(".tool-detail", Static)
        assert detail._render_markup is False
        assert "43f4-4f1c" in str(detail.render())


@pytest.mark.asyncio
async def test_tui_displays_and_resets_live_token_metrics(tmp_path: Path) -> None:
    app = MidasApp(agent=_FakeAgent(), workspace=tmp_path)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        app._research_running = True
        app._started_at = app._started_at or 1.0
        app._record_usage({"input_tokens": 1_200, "output_tokens": 300})
        app._update_brand("⠋  working")

        brand = str(app.query_one("#brand", Static).render())
        assert "IN 1,200" in brand
        assert "OUT 300" in brand
        assert "TPS" in brand

        app._research_running = False
        await app._new_session()
        brand = str(app.query_one("#brand", Static).render())
        assert "IN 0" in brand
        assert "OUT 0" in brand

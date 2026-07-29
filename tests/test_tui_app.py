from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from textual.widgets import Input, Markdown, Static, Tree

from midas.tui.app import MidasApp


class _FakeAgent:
    def __init__(self) -> None:
        self.configs: list[dict[str, Any]] = []

    async def astream(self, payload: Any, **kwargs: Any):
        self.configs.append(kwargs["config"])
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

        assert len(fake.configs) == 2
        assert fake.configs[0]["configurable"]["thread_id"] == fake.configs[1][
            "configurable"
        ]["thread_id"]
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

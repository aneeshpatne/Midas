from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessageChunk
from textual.widgets import Input, Markdown, OptionList, Static, Tree

from midas.deepagents.modes import ResearchMode
from midas.tui.app import ChatTranscript, MidasApp
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
                "model": {"todos": [{"content": "Research universe", "status": "in_progress"}]}
            },
        }


class _InvalidToolHistoryAgent:
    async def astream(self, payload: Any, **kwargs: Any):
        if False:
            yield None
        raise RuntimeError("insufficient tool messages following tool_calls message")


@pytest.mark.asyncio
async def test_transcript_coalesces_streamed_markdown_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = MidasApp(agent=_FakeAgent(), workspace=tmp_path)
    update_calls = 0
    original_update = Markdown.update

    async def counted_update(self: Markdown, markdown: str):
        nonlocal update_calls
        update_calls += 1
        return await original_update(self, markdown)

    monkeypatch.setattr(Markdown, "update", counted_update)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        transcript = app.query_one(ChatTranscript)
        for index in range(100):
            await transcript.append_text(
                AgentEvent(
                    EventKind.TEXT,
                    "midas-lead-analyst",
                    str(index % 10),
                    "long-answer",
                )
            )

        calls_before_final_flush = update_calls
        await transcript.flush_streams()

        message = transcript.query_one(".bubble.agent", Markdown)
        assert message.source.endswith("".join(str(index % 10) for index in range(100)))
        assert calls_before_final_flush < 10
        assert update_calls <= calls_before_final_flush + 1


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
        assert fake.calls[1][1]["config"]["configurable"]["thread_id"] == app.thread_id
        assert "Research universe" in str(app.query_one("#todos", Static).render())
        assert prompt.disabled is False


@pytest.mark.asyncio
async def test_slash_menu_opens_filters_and_keeps_prompt_focus(tmp_path: Path) -> None:
    app = MidasApp(agent=_FakeAgent(), workspace=tmp_path)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", Input)
        menu = app.query_one("#slash-command-list", OptionList)
        prompt.value = "/"
        await pilot.pause()

        assert menu.has_class("visible")
        assert [menu.get_option_at_index(index).id for index in range(menu.option_count)] == [
            "/new",
            "/resume",
            "/sessions",
            "/exit",
            "/quit",
        ]
        assert app.focused is prompt

        prompt.value = "/RE"
        await pilot.pause()

        assert menu.option_count == 1
        assert menu.get_option_at_index(0).id == "/resume"
        assert app.focused is prompt


@pytest.mark.asyncio
async def test_slash_menu_hides_for_normal_arguments_and_unknown_prefix(
    tmp_path: Path,
) -> None:
    app = MidasApp(agent=_FakeAgent(), workspace=tmp_path)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", Input)
        menu = app.query_one("#slash-command-list", OptionList)
        for value in ("NIFTY IT", "/resume abc", "/unknown"):
            prompt.value = value
            await pilot.pause()
            assert not menu.has_class("visible")


@pytest.mark.asyncio
async def test_slash_menu_arrows_and_tab_complete_without_moving_focus(
    tmp_path: Path,
) -> None:
    app = MidasApp(agent=_FakeAgent(), workspace=tmp_path)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", Input)
        menu = app.query_one("#slash-command-list", OptionList)
        prompt.value = "/"
        await pilot.pause()

        await pilot.press("down")
        assert menu.highlighted == 1
        await pilot.press("up")
        assert menu.highlighted == 0
        assert app.focused is prompt

        prompt.value = "/re"
        await pilot.pause()
        await pilot.press("tab")

        assert prompt.value == "/resume "
        assert prompt.cursor_position == len(prompt.value)
        assert not menu.has_class("visible")
        assert app.focused is prompt


@pytest.mark.asyncio
async def test_enter_completes_command_before_executing_it(tmp_path: Path) -> None:
    app = MidasApp(agent=_FakeAgent(), workspace=tmp_path)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", Input)
        old_thread = app.thread_id
        prompt.value = "/n"
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        assert prompt.value == "/new"
        assert app.thread_id == old_thread

        await pilot.press("enter")
        await pilot.pause(0.2)

        assert app.thread_id != old_thread


@pytest.mark.asyncio
async def test_escape_dismisses_slash_menu_until_input_changes(tmp_path: Path) -> None:
    app = MidasApp(agent=_FakeAgent(), workspace=tmp_path)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", Input)
        menu = app.query_one("#slash-command-list", OptionList)
        prompt.value = "/"
        await pilot.pause()

        await pilot.press("escape")
        assert prompt.value == "/"
        assert not menu.has_class("visible")
        assert app.focused is prompt

        prompt.value = "/r"
        await pilot.pause()
        assert menu.has_class("visible")


@pytest.mark.asyncio
async def test_option_selection_and_unknown_slash_passthrough(tmp_path: Path) -> None:
    fake = _FakeAgent()
    app = MidasApp(agent=fake, workspace=tmp_path)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", Input)
        menu = app.query_one("#slash-command-list", OptionList)
        prompt.value = "/s"
        await pilot.pause()
        menu.action_select()
        await pilot.pause()

        assert prompt.value == "/sessions"
        assert not menu.has_class("visible")

        prompt.value = "/analyse-this"
        await pilot.press("enter")
        await pilot.pause(0.2)

        assert fake.calls[0][0]["messages"] == [("user", "/analyse-this")]


@pytest.mark.asyncio
async def test_tab_falls_through_and_slash_menu_fits_narrow_layout(tmp_path: Path) -> None:
    app = MidasApp(agent=_FakeAgent(), workspace=tmp_path)

    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", Input)
        menu = app.query_one("#slash-command-list", OptionList)
        prompt.value = "/"
        await pilot.pause()

        assert menu.region.y < prompt.region.y
        assert menu.region.bottom <= prompt.region.y

        await pilot.press("escape")
        await pilot.press("tab")
        assert app.focused is not prompt


@pytest.mark.asyncio
async def test_tui_tracks_and_previews_session_markdown(tmp_path: Path) -> None:
    app = MidasApp(agent=_FakeAgent(), workspace=tmp_path)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        artifact = app.session_output_directory / "research" / "nifty-it" / "run" / "00_mandate.md"
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
        assert app.thread_id in app.query_one("#file-tree", Tree).root.label.plain


def test_shift_tab_binding_is_priority_mode_switch() -> None:
    binding = next(binding for binding in MidasApp.BINDINGS if binding.key == "shift+tab")

    assert binding.priority is True
    assert binding.action == "switch_research_mode"


@pytest.mark.asyncio
async def test_shift_tab_switches_owned_agent_into_fresh_focused_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from midas.deepagents import deepagent

    calls: list[tuple[ResearchMode, str]] = []

    def fake_factory(mode: ResearchMode, *, agent_id: str, workspace: Path):
        calls.append((mode, agent_id))
        return _FakeAgent()

    monkeypatch.setattr(deepagent, "create_research_agent", fake_factory)
    app = MidasApp(workspace=tmp_path)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause(0.2)
        old_thread = app.thread_id
        prompt = app.query_one("#prompt", Input)
        menu = app.query_one("#slash-command-list", OptionList)
        prompt.value = "/"
        await pilot.pause()
        assert menu.has_class("visible")
        await pilot.press("shift+tab")
        await pilot.pause(0.2)

        assert app.research_mode == ResearchMode.SINGLE_STOCK
        assert app.thread_id != old_thread
        assert not menu.has_class("visible")
        assert calls == [
            (ResearchMode.DEEP_WIDE, old_thread),
            (ResearchMode.SINGLE_STOCK, app.thread_id),
        ]
        assert app._sessions.get(old_thread).mode == ResearchMode.DEEP_WIDE
        assert app._sessions.get(app.thread_id).mode == ResearchMode.SINGLE_STOCK
        assert "one company" in app.query_one("#prompt", Input).placeholder.lower()
        assert "Single Stock Research Agent" in str(app.query_one("#brand", Static).render())


@pytest.mark.asyncio
async def test_mode_switch_is_blocked_during_research(tmp_path: Path) -> None:
    app = MidasApp(agent=_FakeAgent(), workspace=tmp_path)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        old_thread = app.thread_id
        app._research_running = True

        await app._switch_research_mode()

        app._research_running = False
        assert app.research_mode == ResearchMode.DEEP_WIDE
        assert app.thread_id == old_thread
        assert any(
            "Finish or cancel" in str(widget.render()) for widget in app.query("#transcript Static")
        )


@pytest.mark.asyncio
async def test_resume_restores_conversation_and_session_files(tmp_path: Path) -> None:
    app = MidasApp(agent=_FakeAgent(), workspace=tmp_path)

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        original_id = app.thread_id
        app._conversation = [("user", "NIFTY IT"), ("assistant", "Prior answer")]
        app._save_session()
        artifact = app.session_output_directory / "research" / "nifty-it" / "run" / "00_mandate.md"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("# Mandate", encoding="utf-8")

        await app._new_session()
        await app._resume_session(original_id[:10])

        assert app.thread_id == original_id
        assert app._conversation[-1] == ("assistant", "Prior answer")
        assert artifact.resolve() in app._session_files
        restored_messages = app.query("#transcript Markdown")
        assert any("Prior answer" in message.source for message in restored_messages)


@pytest.mark.asyncio
async def test_resume_restores_saved_research_mode(tmp_path: Path) -> None:
    app = MidasApp(
        agent=_FakeAgent(),
        workspace=tmp_path,
        mode=ResearchMode.SINGLE_STOCK,
    )

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        focused_id = app.thread_id
        app._conversation = [("user", "TCS"), ("assistant", "Focused answer")]
        app._save_session()
        app.research_mode = ResearchMode.DEEP_WIDE
        await app._new_session(save_current=False)

        await app._resume_session(focused_id)

        assert app.research_mode == ResearchMode.SINGLE_STOCK
        assert "one company" in app.query_one("#prompt", Input).placeholder.lower()
        assert "Single Stock Research Agent" in str(app.query_one("#brand", Static).render())


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

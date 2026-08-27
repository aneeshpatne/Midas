"""Textual application for conversational Midas research."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from rich.markup import escape
from textual import work
from textual.actions import SkipAction
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Resize
from textual.widgets import Collapsible, Footer, Input, Markdown, OptionList, Static, Tree
from textual.widgets.option_list import Option
from textual.widgets.tree import TreeNode
from textual.worker import Worker

from ..deepagents.modes import (
    DEFAULT_RESEARCH_MODE,
    LEGACY_ROOT_AGENT_ID,
    ResearchMode,
    ResearchModeSpec,
    next_research_mode,
    normalize_research_mode,
    research_mode_spec,
)
from ..sessions import Session, SessionStore
from .events import AGENT_LABELS, AgentEvent, EventKind, display_agent, stream_agent_events

_SPLASH_FRAMES = (
    "     ╭─────╮\n   ╭─┤  ◇  ├─╮\n     ╰─────╯",
    "     ╭─────╮\n  ───┤  ◆  ├───\n     ╰─────╯",
    "     ╭─────╮\n   ╰─┤  ◇  ├─╯\n     ╰─────╯",
)

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SECRET_WORDS = ("api_key", "apikey", "authorization", "password", "secret", "token")
_STREAM_RENDER_INTERVAL = 0.05


@dataclass(frozen=True, slots=True)
class _SlashCommand:
    """One discoverable command accepted by the prompt."""

    token: str
    description: str
    completion: str


_SLASH_COMMANDS = (
    _SlashCommand("/new", "Start a fresh session in the current mode", "/new"),
    _SlashCommand("/resume", "Resume the latest or a matching session", "/resume "),
    _SlashCommand("/sessions", "List recent resumable sessions", "/sessions"),
    _SlashCommand("/exit", "Save the current session and exit", "/exit"),
    _SlashCommand("/quit", "Save the current session and exit", "/quit"),
)
_SLASH_COMMANDS_BY_TOKEN = {command.token: command for command in _SLASH_COMMANDS}


class _SlashCommandList(OptionList, can_focus=False):
    """Visible slash completions that leave keyboard focus in the prompt."""


class _PromptInput(Input):
    """Prompt input with keyboard delegation to the slash-command menu."""

    BINDINGS = [
        *Input.BINDINGS,
        Binding("up", "slash_cursor_up", show=False),
        Binding("down", "slash_cursor_down", show=False),
        Binding("tab", "slash_complete", show=False),
        Binding("escape", "slash_dismiss", show=False),
    ]

    def action_slash_cursor_up(self) -> None:
        if not self.app._move_slash_highlight(-1):
            raise SkipAction

    def action_slash_cursor_down(self) -> None:
        if not self.app._move_slash_highlight(1):
            raise SkipAction

    def action_slash_complete(self) -> None:
        if not self.app._complete_highlighted_slash_command():
            raise SkipAction

    def action_slash_dismiss(self) -> None:
        if not self.app._dismiss_slash_commands(suppress_current=True):
            raise SkipAction

    async def action_submit(self) -> None:
        if self.app._complete_highlighted_slash_command():
            return
        await super().action_submit()


@dataclass(slots=True)
class _StreamBuffer:
    """Chunks for a streamed widget that have not all been rendered yet."""

    widget: Markdown | Static
    chunks: list[str] = field(default_factory=list)


def _safe_detail(value: Any, *, limit: int = 20_000) -> str:
    """Render event detail without leaking common credential fields."""

    def clean(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                str(key): "[redacted]"
                if any(word in str(key).lower() for word in _SECRET_WORDS)
                else clean(child)
                for key, child in item.items()
            }
        if isinstance(item, (list, tuple)):
            return [clean(child) for child in item]
        return item

    if isinstance(value, str):
        rendered = value
    else:
        try:
            rendered = json.dumps(clean(value), indent=2, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            rendered = str(value)
    if len(rendered) > limit:
        return f"{rendered[:limit]}\n… output truncated in the TUI ({len(rendered):,} chars total)"
    return rendered


class ChatTranscript(VerticalScroll):
    """Scrollable chat and activity feed with incrementally updated messages."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._streams: dict[tuple[str, str], _StreamBuffer] = {}
        self._reasoning: dict[tuple[str, str], _StreamBuffer] = {}
        self._tools: dict[str, Collapsible] = {}
        self._dirty_streams: set[tuple[str, str]] = set()
        self._dirty_reasoning: set[tuple[str, str]] = set()
        self._flush_scheduled = False

    def _scroll_to_end(self, *, force: bool = False) -> None:
        """Follow new output without repeatedly re-laying out a scrolled-up chat."""
        if force or self.is_vertical_scroll_end:
            self.scroll_end(animate=False)

    def _schedule_flush(self) -> None:
        if self._flush_scheduled:
            return
        self._flush_scheduled = True
        self.set_timer(_STREAM_RENDER_INTERVAL, self._flush_pending)

    async def _flush_pending(self) -> None:
        self._flush_scheduled = False
        await self.flush_streams()

    async def flush_streams(self) -> None:
        """Render all buffered stream chunks, coalescing layout and Markdown work."""
        stream_keys = tuple(self._dirty_streams)
        reasoning_keys = tuple(self._dirty_reasoning)
        self._dirty_streams.difference_update(stream_keys)
        self._dirty_reasoning.difference_update(reasoning_keys)
        follow_output = self.is_vertical_scroll_end

        for key in stream_keys:
            stream = self._streams.get(key)
            if stream is None:
                continue
            content = "".join(stream.chunks)
            await stream.widget.update(f"**{display_agent(key[0])}**\n\n{content}")
        for key in reasoning_keys:
            stream = self._reasoning.get(key)
            if stream is not None:
                stream.widget.update(_safe_detail("".join(stream.chunks)))

        if follow_output and (stream_keys or reasoning_keys):
            self.scroll_end(animate=False)
        if self._dirty_streams or self._dirty_reasoning:
            self._schedule_flush()

    async def add_user(self, text: str) -> None:
        await self.mount(Static(f"[b]You[/b]\n{escape(text)}", classes="bubble user"))
        self._scroll_to_end(force=True)

    async def add_system(self, text: str, *, error: bool = False) -> None:
        classes = "activity error" if error else "activity system"
        await self.mount(Static(escape(text), classes=classes))
        self._scroll_to_end(force=True)

    async def append_text(self, event: AgentEvent) -> None:
        event_id = event.event_id or f"{event.agent}-message"
        key = (event.agent, event_id)
        existing = self._streams.get(key)
        if existing is None:
            widget = Markdown(
                f"**{display_agent(event.agent)}**\n\n{event.content}",
                classes=f"bubble agent {event.agent}",
            )
            self._streams[key] = _StreamBuffer(widget, [str(event.content)])
            await self.mount(widget)
            self._scroll_to_end(force=True)
        else:
            existing.chunks.append(str(event.content))
            self._dirty_streams.add(key)
            self._schedule_flush()

    async def add_activity(self, event: AgentEvent) -> None:
        label = display_agent(event.agent)
        if event.kind == EventKind.UPDATE:
            title = event.title or "Research update"
            await self.mount(
                Collapsible(
                    Static(_safe_detail(event.content), markup=False),
                    title=f"{label} · {title}",
                    collapsed=False,
                    classes="activity update",
                )
            )
        elif event.kind == EventKind.REASONING:
            event_id = event.event_id or f"{event.agent}-reasoning"
            key = (event.agent, event_id)
            existing = self._reasoning.get(key)
            if existing is None:
                detail = Static(_safe_detail(event.content), markup=False)
                self._reasoning[key] = _StreamBuffer(detail, [str(event.content)])
                await self.mount(
                    Collapsible(
                        detail,
                        title=f"{label} · reasoning/status",
                        collapsed=False,
                        classes="activity reasoning",
                    )
                )
            else:
                existing.chunks.append(str(event.content))
                self._dirty_reasoning.add(key)
                self._schedule_flush()
        elif event.kind == EventKind.TOOL_STARTED:
            title = event.title or "tool"
            widget = Collapsible(
                Static(_safe_detail(event.content), markup=False, classes="tool-detail"),
                title=f"◌ {label} · {title}",
                collapsed=True,
                classes="activity tool running",
            )
            if event.event_id:
                self._tools[event.event_id] = widget
            await self.mount(widget)
        elif event.kind in {EventKind.TOOL_FINISHED, EventKind.TOOL_ERROR}:
            tool = self._tools.get(event.event_id or "")
            marker = "✕" if event.kind == EventKind.TOOL_ERROR else "✓"
            state = "failed" if event.kind == EventKind.TOOL_ERROR else "finished"
            if tool is None:
                tool = Collapsible(
                    Static(
                        _safe_detail(event.content),
                        markup=False,
                        classes="tool-detail",
                    ),
                    title=f"{marker} {label} · {event.title or 'tool'}",
                    collapsed=True,
                    classes=f"activity tool {state}",
                )
                await self.mount(tool)
            else:
                tool.title = f"{marker} {label} · {event.title or 'tool'}"
                tool.remove_class("running")
                tool.add_class(state)
                detail = tool.query_one(".tool-detail", Static)
                detail.update(_safe_detail(event.content))
        self._scroll_to_end(force=True)

    async def reset_feed(self) -> None:
        await self.remove_children()
        self._streams.clear()
        self._reasoning.clear()
        self._tools.clear()
        self._dirty_streams.clear()
        self._dirty_reasoning.clear()


class MidasApp(App[None]):
    """Codex-like terminal chat for the staged Midas agent."""

    TITLE = "Midas"
    SUB_TITLE = "Agentic equity research"
    ENABLE_COMMAND_PALETTE = False

    CSS = """
    Screen {
        background: #080b10;
        color: #d7dae0;
    }
    #brand {
        height: 3;
        padding: 0 2;
        content-align: left middle;
        background: #111722;
        color: #f4bd50;
        text-style: bold;
        border-bottom: solid #604a22;
    }
    #body { height: 1fr; }
    #sidebar {
        width: 29;
        min-width: 24;
        padding: 1;
        border-right: solid #293142;
        background: #0c1119;
    }
    #main { width: 1fr; }
    #files {
        width: 43;
        min-width: 32;
        border-left: solid #293142;
        background: #0c1119;
    }
    .pane-title {
        height: 2;
        color: #f4bd50;
        text-style: bold;
    }
    .agent-row {
        height: 2;
        padding: 0 1;
        color: #7e8797;
    }
    .agent-row.active {
        color: #17120a;
        background: #f4bd50;
        text-style: bold;
    }
    #todos {
        margin-top: 1;
        height: auto;
        color: #a9b1be;
    }
    #transcript {
        height: 1fr;
        padding: 1 2;
        scrollbar-color: #604a22;
    }
    .bubble {
        margin: 0 0 1 0;
        padding: 1 2;
        height: auto;
    }
    .bubble.user {
        margin-left: 8;
        background: #1b2432;
        border: round #3c4d68;
    }
    .bubble.agent {
        margin-right: 5;
        background: #10151e;
        border-left: thick #c89335;
    }
    .activity {
        margin: 0 2 1 1;
        height: auto;
        color: #aeb6c3;
    }
    .activity.update { border-left: solid #377f77; }
    .activity.reasoning { border-left: solid #65568c; }
    .activity.tool { border-left: solid #735d32; }
    .activity.tool.finished { border-left: solid #3f7950; }
    .activity.tool.failed, .error { border-left: solid #a84848; color: #f19999; }
    .activity.system { color: #8893a4; padding: 1 2; }
    #prompt-area {
        dock: bottom;
        height: auto;
    }
    #slash-command-list {
        display: none;
        height: auto;
        max-height: 7;
        margin: 0 2;
        padding: 0 1;
        border: tall #604a22;
        background: #111722;
        scrollbar-color: #604a22;
    }
    #slash-command-list.visible { display: block; }
    #slash-command-list > .option-list--option-highlighted {
        color: #17120a;
        background: #f4bd50;
        text-style: bold;
    }
    #prompt {
        margin: 0 2 1 2;
        border: tall #604a22;
        background: #111722;
    }
    #prompt:focus { border: tall #f4bd50; }
    #file-tree {
        height: 2fr;
        border-bottom: solid #293142;
        scrollbar-color: #604a22;
    }
    #preview {
        height: 3fr;
        padding: 1;
        scrollbar-color: #604a22;
    }
    #splash {
        layer: overlay;
        width: 42;
        height: 12;
        align: center middle;
        content-align: center middle;
        background: #0c1119;
        color: #f4bd50;
        border: double #f4bd50;
        text-align: center;
    }
    #splash.hidden { display: none; }
    .hidden-pane { display: none; }
    Footer {
        background: #111722;
        color: #8f99a8;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "cancel_or_quit", "Cancel / quit", priority=True),
        Binding("ctrl+n", "new_session", "New session"),
        Binding("shift+tab", "switch_research_mode", "Switch research mode", priority=True),
        Binding("f2", "toggle_sidebar", "Agents"),
        Binding("f3", "toggle_files", "Files"),
    ]

    def __init__(
        self,
        *,
        agent: Any | None = None,
        workspace: Path | None = None,
        mode: ResearchMode = DEFAULT_RESEARCH_MODE,
    ) -> None:
        super().__init__()
        self.research_agent = agent
        self._owns_agent = agent is None
        self.research_mode = normalize_research_mode(mode)
        self.workspace = (workspace or Path.cwd()).resolve()
        self.thread_id = uuid.uuid4().hex
        self._sessions = SessionStore(self.workspace / "output" / ".midas-sessions.sqlite3")
        self._sessions.create(self.thread_id, mode=self.research_mode)
        self._conversation: list[tuple[str, str]] = []
        self._worker: Worker[Any] | None = None
        self._initializing = True
        self._research_running = False
        self._active_agent = ""
        self._started_at = 0.0
        self._turn_output_tokens = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._animation_index = 0
        self._reduced_motion = bool(os.getenv("NO_COLOR"))
        self._known_files: dict[Path, int] = self._scan_markdown()
        self._session_files: dict[Path, int] = {}
        self._slash_menu_suppressed_value: str | None = None

    @property
    def session_output_directory(self) -> Path:
        """Physical directory that is exposed as `/` to the current agent."""
        return (self.workspace / "output" / self.thread_id).resolve()

    @property
    def mode_spec(self) -> ResearchModeSpec:
        """Metadata for the active top-level research mode."""
        return research_mode_spec(self.research_mode)

    @property
    def root_agent_id(self) -> str:
        """Graph identity whose text is persisted as the assistant answer."""
        return self.mode_spec.root_agent_id

    def compose(self) -> ComposeResult:
        yield Static(f"MIDAS  ◇  {self.mode_spec.label}  ·  initializing", id="brand")
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("AGENTS", classes="pane-title")
                for agent, label in AGENT_LABELS.items():
                    if agent == LEGACY_ROOT_AGENT_ID:
                        continue
                    yield Static(f"○  {label}", id=f"agent-{agent}", classes="agent-row")
                yield Static("TODOS", classes="pane-title")
                yield Static("No todos yet", id="todos")
            with Vertical(id="main"):
                yield ChatTranscript(id="transcript")
                with Vertical(id="prompt-area"):
                    yield _SlashCommandList(id="slash-command-list", markup=False)
                    yield _PromptInput(
                        placeholder=self.mode_spec.prompt_placeholder,
                        id="prompt",
                    )
            with Vertical(id="files"):
                yield Static("SESSION MARKDOWN", classes="pane-title")
                yield Tree("No files yet", id="file-tree")
                yield Markdown("_Select a Markdown artifact to preview it._", id="preview")
        yield Static("", id="splash")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#prompt", Input).disabled = True
        self.set_interval(0.12, self._tick_animation)
        self.set_interval(0.5, self._refresh_files)
        self.initialize_agent()

    async def _build_owned_agent(self) -> None:
        if not self._owns_agent:
            return
        from ..deepagents.deepagent import create_research_agent

        self.research_agent = await asyncio.to_thread(
            create_research_agent,
            self.research_mode,
            agent_id=self.thread_id,
            workspace=self.workspace,
        )

    def _refresh_mode_ui(self) -> None:
        self.query_one("#prompt", Input).placeholder = self.mode_spec.prompt_placeholder
        self._update_brand("◆  ready")

    @work(exclusive=True, group="initialization")
    async def initialize_agent(self) -> None:
        load_dotenv()
        splash = self.query_one("#splash", Static)
        splash.update(f"{_SPLASH_FRAMES[0]}\n\nMIDAS\nWaking {self.mode_spec.label}…")
        try:
            if self.research_agent is None:
                await self._build_owned_agent()
            missing = [
                name for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY") if not os.getenv(name)
            ]
            if missing:
                await self.query_one(ChatTranscript).add_system(
                    f"Missing {', '.join(missing)}. Add credentials to .env before starting "
                    "research.",
                    error=True,
                )
            else:
                await self.query_one(ChatTranscript).add_system(
                    f"{self.mode_spec.label} ready. Press Shift+Tab to switch modes; "
                    "use /new, /resume [session-id], or /exit."
                )
            self.query_one("#prompt", Input).disabled = False
            self.query_one("#prompt", Input).focus()
            self._update_brand("◆  ready")
        except Exception as exc:
            await self.query_one(ChatTranscript).add_system(
                f"Agent initialization failed: {exc}", error=True
            )
            self.query_one("#brand", Static).update("MIDAS  ✕  initialization failed")
        finally:
            self._initializing = False
            splash.add_class("hidden")

    def _tick_animation(self) -> None:
        if not self.is_mounted:
            return
        if self._reduced_motion:
            if self._research_running:
                agent = display_agent(self._active_agent or self.root_agent_id)
                self._update_brand(f"…  {agent} working")
            return
        self._animation_index += 1
        splash = next(iter(self.query("#splash")), None)
        if not isinstance(splash, Static):
            return
        if not splash.has_class("hidden"):
            frame = _SPLASH_FRAMES[self._animation_index % len(_SPLASH_FRAMES)]
            splash.update(f"{frame}\n\nMIDAS\nWaking {self.mode_spec.label}…")
        if self._research_running:
            spinner = _SPINNER[self._animation_index % len(_SPINNER)]
            elapsed = time.monotonic() - self._started_at
            agent = display_agent(self._active_agent or self.root_agent_id)
            self._update_brand(f"{spinner}  {agent} working  ·  {elapsed:,.0f}s")

    def _update_brand(self, state: str) -> None:
        elapsed = time.monotonic() - self._started_at if self._research_running else 0.0
        tps = self._turn_output_tokens / elapsed if elapsed > 0 else 0.0
        self.query_one("#brand", Static).update(
            f"MIDAS  {state}  ·  {self.mode_spec.label}  ·  {tps:,.1f} TPS  ·  "
            f"IN {self._total_input_tokens:,}  OUT {self._total_output_tokens:,}"
        )

    def _record_usage(self, usage: Any) -> None:
        if not isinstance(usage, dict):
            return
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        if not isinstance(input_tokens, int) or isinstance(input_tokens, bool):
            input_tokens = 0
        if not isinstance(output_tokens, int) or isinstance(output_tokens, bool):
            output_tokens = 0
        self._total_input_tokens += max(0, input_tokens)
        self._total_output_tokens += max(0, output_tokens)
        self._turn_output_tokens += max(0, output_tokens)

    def _slash_commands_visible(self) -> bool:
        return self.query_one("#slash-command-list", _SlashCommandList).has_class("visible")

    def _refresh_slash_commands(self, value: str) -> None:
        menu = self.query_one("#slash-command-list", _SlashCommandList)
        if value == self._slash_menu_suppressed_value:
            menu.remove_class("visible")
            menu.clear_options()
            return
        self._slash_menu_suppressed_value = None
        if not value.startswith("/") or any(character.isspace() for character in value):
            self._dismiss_slash_commands()
            return
        matches = [
            command
            for command in _SLASH_COMMANDS
            if command.token.casefold().startswith(value.casefold())
        ]
        if not matches:
            self._dismiss_slash_commands()
            return
        menu.set_options(
            [
                Option(
                    f"{command.token}  —  {command.description}",
                    id=command.token,
                )
                for command in matches
            ]
        )
        menu.highlighted = 0
        menu.add_class("visible")

    def _move_slash_highlight(self, direction: int) -> bool:
        if not self._slash_commands_visible():
            return False
        menu = self.query_one("#slash-command-list", _SlashCommandList)
        if direction < 0:
            menu.action_cursor_up()
        else:
            menu.action_cursor_down()
        return True

    def _complete_highlighted_slash_command(self) -> bool:
        if not self._slash_commands_visible():
            return False
        menu = self.query_one("#slash-command-list", _SlashCommandList)
        if menu.highlighted is None:
            return False
        option = menu.get_option_at_index(menu.highlighted)
        command = _SLASH_COMMANDS_BY_TOKEN.get(str(option.id))
        if command is None:
            return False
        prompt = self.query_one("#prompt", _PromptInput)
        self._slash_menu_suppressed_value = command.completion
        prompt.value = command.completion
        prompt.action_end()
        self._dismiss_slash_commands()
        prompt.focus()
        return True

    def _dismiss_slash_commands(self, *, suppress_current: bool = False) -> bool:
        menu = self.query_one("#slash-command-list", _SlashCommandList)
        was_visible = menu.has_class("visible")
        if suppress_current:
            self._slash_menu_suppressed_value = self.query_one("#prompt", _PromptInput).value
        menu.remove_class("visible")
        menu.clear_options()
        return was_visible

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "prompt":
            self._refresh_slash_commands(event.value)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "slash-command-list":
            return
        event.stop()
        command = _SLASH_COMMANDS_BY_TOKEN.get(str(event.option.id))
        if command is None:
            return
        menu = self.query_one("#slash-command-list", _SlashCommandList)
        menu.highlighted = event.option_index
        self._complete_highlighted_slash_command()

    async def _dispatch_slash_command(self, command: str, argument: str) -> bool:
        if command not in _SLASH_COMMANDS_BY_TOKEN:
            return False
        if command in {"/exit", "/quit"}:
            self._save_session()
            self.exit()
        elif command == "/new":
            await self._new_session()
        elif command == "/resume":
            await self._resume_session(argument)
        elif command == "/sessions":
            await self._show_sessions()
        return True

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value or self._research_running:
            return
        self._dismiss_slash_commands()
        event.input.value = ""
        command, _, argument = value.partition(" ")
        if await self._dispatch_slash_command(command, argument):
            return
        await self.query_one(ChatTranscript).add_user(value)
        self._research_running = True
        self._started_at = time.monotonic()
        self._turn_output_tokens = 0
        self._active_agent = self.root_agent_id
        event.input.disabled = True
        self._set_active_agent(self._active_agent)
        self._worker = self.run_research(value)

    @work(exclusive=True, group="research")
    async def run_research(self, prompt: str) -> None:
        from ..deepagents.workspace import AGENT_OUTPUT_DIRECTORY

        transcript = self.query_one(ChatTranscript)
        root_answers: dict[str, list[str]] = {}
        workspace_token = AGENT_OUTPUT_DIRECTORY.set(self.session_output_directory)
        try:
            async for event in stream_agent_events(
                self.research_agent,
                prompt,
                root_agent_id=self.root_agent_id,
                history=self._conversation,
                config={"configurable": {"thread_id": self.thread_id}},
            ):
                if event.agent:
                    self._active_agent = event.agent
                    self._set_active_agent(event.agent)
                if event.kind == EventKind.TEXT:
                    await transcript.append_text(event)
                    if event.agent == self.root_agent_id:
                        message_id = event.event_id or "root-answer"
                        root_answers.setdefault(message_id, []).append(str(event.content))
                elif event.kind == EventKind.TODOS:
                    self._render_todos(event.content)
                elif event.kind == EventKind.USAGE:
                    self._record_usage(event.content)
                elif event.kind == EventKind.STATUS:
                    await transcript.flush_streams()
                    continue
                else:
                    await transcript.add_activity(event)
            if root_answers:
                final_answer = "".join(next(reversed(root_answers.values())))
                self._conversation.extend([("user", prompt), ("assistant", final_answer)])
                self._save_session()
            await transcript.add_system("Turn completed.")
            self._update_brand("◆  ready")
        except asyncio.CancelledError:
            await transcript.add_system("Research cancelled.")
            self._update_brand("◇  cancelled")
        except Exception as exc:
            if "insufficient tool messages following tool_calls" in str(exc):
                self._conversation.clear()
                self._save_session()
                await transcript.add_system(
                    "The provider rejected an incomplete tool-call batch. Internal "
                    "conversation state was cleared automatically; generated files "
                    "were left untouched. You can resubmit the request safely.",
                    error=True,
                )
            await transcript.add_system(f"Research failed: {exc}", error=True)
            self._update_brand("✕  failed")
        finally:
            AGENT_OUTPUT_DIRECTORY.reset(workspace_token)
            self._research_running = False
            self._set_active_agent("")
            prompt_input = self.query_one("#prompt", Input)
            prompt_input.disabled = False
            prompt_input.focus()

    def _set_active_agent(self, active: str) -> None:
        for agent in AGENT_LABELS:
            if agent == LEGACY_ROOT_AGENT_ID:
                continue
            row = self.query_one(f"#agent-{agent}", Static)
            row.set_class(agent == active, "active")
            marker = "◆" if agent == active else "○"
            row.update(f"{marker}  {AGENT_LABELS[agent]}")

    def _render_todos(self, todos: Any) -> None:
        if not isinstance(todos, list) or not todos:
            self.query_one("#todos", Static).update("No todos yet")
            return
        markers = {"pending": "○", "in_progress": "◉", "completed": "✓"}
        lines = []
        for todo in todos:
            if not isinstance(todo, dict):
                continue
            status = str(todo.get("status", "pending"))
            lines.append(f"{markers.get(status, '○')} {escape(str(todo.get('content', '')))}")
        self.query_one("#todos", Static).update("\n".join(lines))

    def _scan_markdown(self) -> dict[Path, int]:
        root = self.session_output_directory / "research"
        if not root.exists():
            return {}
        files: dict[Path, int] = {}
        for path in root.rglob("*.md"):
            try:
                files[path.resolve()] = path.stat().st_mtime_ns
            except OSError:
                continue
        return files

    def _refresh_files(self) -> None:
        current = self._scan_markdown()
        changed = {
            path: mtime
            for path, mtime in current.items()
            if path not in self._known_files or self._known_files[path] != mtime
        }
        if changed:
            selected = self.query_one("#file-tree", Tree).cursor_node
            selected_path = selected.data if selected and isinstance(selected.data, Path) else None
            self._session_files.update(changed)
            self._rebuild_tree(selected_path)
            if selected_path is not None:
                self._preview_file(selected_path)
        self._known_files = current

    def _rebuild_tree(self, selected_path: Path | None = None) -> None:
        tree = self.query_one("#file-tree", Tree)
        tree.reset(f"output/{self.thread_id}/research")
        root = tree.root
        nodes: dict[tuple[str, ...], TreeNode[Any]] = {(): root}
        leaves: dict[Path, TreeNode[Any]] = {}
        research_root = self.session_output_directory / "research"
        for path in sorted(self._session_files):
            try:
                parts = path.relative_to(research_root).parts
            except ValueError:
                continue
            parent_key: tuple[str, ...] = ()
            for part in parts[:-1]:
                key = (*parent_key, part)
                if key not in nodes:
                    nodes[key] = nodes[parent_key].add(part)
                parent_key = key
            leaves[path] = nodes[parent_key].add_leaf(parts[-1], data=path)
        root.expand_all()
        if selected_path in leaves:
            tree.select_node(leaves[selected_path])

    def on_tree_node_selected(self, event: Tree.NodeSelected[Any]) -> None:
        if isinstance(event.node.data, Path):
            self._preview_file(event.node.data)

    def _preview_file(self, path: Path) -> None:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            content = f"# Unable to read file\n\n{exc}"
        self.query_one("#preview", Markdown).update(content)

    async def _new_session(self, *, save_current: bool = True) -> None:
        self._dismiss_slash_commands()
        if save_current:
            self._save_session()
        self.thread_id = uuid.uuid4().hex
        self._sessions.create(self.thread_id, mode=self.research_mode)
        self._conversation.clear()
        self._turn_output_tokens = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._session_files.clear()
        if self._owns_agent:
            await self._build_owned_agent()
        self._known_files = self._scan_markdown()
        await self.query_one(ChatTranscript).reset_feed()
        await self.query_one(ChatTranscript).add_system(f"New session {self.thread_id} started.")
        self._render_todos([])
        self._rebuild_tree()
        self._update_brand("◆  ready")

    def _save_session(self) -> None:
        self._sessions.save(
            self.thread_id,
            self._conversation,
            mode=self.research_mode,
            input_tokens=self._total_input_tokens,
            output_tokens=self._total_output_tokens,
        )

    async def _resume_session(self, requested_id: str) -> None:
        self._dismiss_slash_commands()
        target: Session | None
        if requested_id.strip():
            target = self._sessions.resolve(requested_id)
        else:
            recent = self._sessions.recent(exclude=self.thread_id, limit=1)
            target = recent[0] if recent else None
        transcript = self.query_one(ChatTranscript)
        if target is None:
            await transcript.add_system(
                "Session not found. Use /sessions to see resumable IDs.", error=True
            )
            return
        if target.session_id == self.thread_id:
            await transcript.add_system(f"Session {self.thread_id} is already active.")
            return

        self._save_session()
        self.thread_id = target.session_id
        self.research_mode = target.mode
        self._conversation = list(target.conversation)
        self._total_input_tokens = target.input_tokens
        self._total_output_tokens = target.output_tokens
        self._turn_output_tokens = 0
        if self._owns_agent:
            await self._build_owned_agent()
        self.query_one("#prompt", Input).placeholder = self.mode_spec.prompt_placeholder
        self._known_files = self._scan_markdown()
        self._session_files = dict(self._known_files)
        await transcript.reset_feed()
        for index, (role, content) in enumerate(self._conversation):
            if role == "user":
                await transcript.add_user(content)
            elif role == "assistant":
                await transcript.append_text(
                    AgentEvent(
                        EventKind.TEXT,
                        self.root_agent_id,
                        content,
                        f"restored-{index}",
                    )
                )
        await transcript.add_system(f"Resumed session {self.thread_id}.")
        self._render_todos([])
        self._rebuild_tree()
        self._update_brand("◆  resumed")

    async def _switch_research_mode(self) -> None:
        self._dismiss_slash_commands()
        transcript = self.query_one(ChatTranscript)
        if self._initializing:
            await transcript.add_system("Wait for agent initialization to finish.", error=True)
            return
        if self._research_running:
            await transcript.add_system(
                "Finish or cancel the active turn before switching research modes.",
                error=True,
            )
            return
        if not self._owns_agent:
            await transcript.add_system(
                "Mode switching is unavailable for an externally supplied agent.",
                error=True,
            )
            return

        self._save_session()
        self.research_mode = next_research_mode(self.research_mode)
        await self._new_session(save_current=False)
        self.query_one("#prompt", Input).placeholder = self.mode_spec.prompt_placeholder
        await self.query_one(ChatTranscript).add_system(
            f"Switched to {self.mode_spec.label}. Session {self.thread_id} started."
        )
        self._update_brand("◆  ready")

    async def _show_sessions(self) -> None:
        sessions = self._sessions.recent(limit=10)
        lines = ["Recent sessions:"]
        for session in sessions:
            marker = "*" if session.session_id == self.thread_id else " "
            title = session.title or "(empty session)"
            mode = research_mode_spec(session.mode).label
            lines.append(f"{marker} {session.session_id}  [{mode}]  {title}")
        await self.query_one(ChatTranscript).add_system("\n".join(lines))

    def action_new_session(self) -> None:
        if not self._research_running:
            self.run_worker(self._new_session())

    def action_switch_research_mode(self) -> None:
        self.run_worker(self._switch_research_mode())

    def action_cancel_or_quit(self) -> None:
        if self._research_running and self._worker is not None:
            self._worker.cancel()
        else:
            self._save_session()
            self.exit()

    def action_toggle_sidebar(self) -> None:
        self.query_one("#sidebar").toggle_class("hidden-pane")

    def action_toggle_files(self) -> None:
        self.query_one("#files").toggle_class("hidden-pane")

    def on_resize(self, event: Resize) -> None:
        """Keep the chat usable on narrow terminals; F2/F3 reveal hidden panes."""
        self.query_one("#files").set_class(event.size.width < 118, "hidden-pane")
        self.query_one("#sidebar").set_class(event.size.width < 82, "hidden-pane")


def main() -> None:
    """Launch the interactive Midas terminal interface.

    Deprecated: prefer the Nilo Electron client with this repo as the workspace
    (Codex / Grok / OpenCode / Deep Agents via ``.nilo/`` + MCP). ``midas-tui``
    remains available temporarily but will be removed.
    """
    import sys
    import warnings

    warnings.warn(
        "midas-tui is deprecated and will be removed; use Nilo with this "
        "workspace instead (equity-data + midas-db MCP).",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        "DEPRECATED: midas-tui is sunset-bound. Prefer Nilo (Codex/Grok/OpenCode) "
        "with this repository as the workspace.",
        file=sys.stderr,
    )
    MidasApp().run()

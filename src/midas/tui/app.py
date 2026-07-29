"""Textual application for conversational Midas research."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from functools import partial
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from rich.markup import escape
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Resize
from textual.widgets import Collapsible, Footer, Input, Markdown, Static, Tree
from textual.widgets.tree import TreeNode
from textual.worker import Worker

from .events import AGENT_LABELS, AgentEvent, EventKind, display_agent, stream_agent_events

_SPLASH_FRAMES = (
    "     ╭─────╮\n   ╭─┤  ◇  ├─╮\n     ╰─────╯",
    "     ╭─────╮\n  ───┤  ◆  ├───\n     ╰─────╯",
    "     ╭─────╮\n   ╰─┤  ◇  ├─╯\n     ╰─────╯",
)

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SECRET_WORDS = ("api_key", "apikey", "authorization", "password", "secret", "token")


def _safe_detail(value: Any, *, limit: int = 20_000) -> str:
    """Render event detail without leaking common credential fields."""

    def clean(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                str(key): "[redacted]" if any(word in str(key).lower() for word in _SECRET_WORDS)
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
        self._streams: dict[tuple[str, str], tuple[Markdown, str]] = {}
        self._reasoning: dict[tuple[str, str], tuple[Static, str]] = {}
        self._tools: dict[str, Collapsible] = {}

    async def add_user(self, text: str) -> None:
        await self.mount(Static(f"[b]You[/b]\n{escape(text)}", classes="bubble user"))
        self.scroll_end(animate=False)

    async def add_system(self, text: str, *, error: bool = False) -> None:
        classes = "activity error" if error else "activity system"
        await self.mount(Static(escape(text), classes=classes))
        self.scroll_end(animate=False)

    async def append_text(self, event: AgentEvent) -> None:
        event_id = event.event_id or f"{event.agent}-message"
        key = (event.agent, event_id)
        existing = self._streams.get(key)
        if existing is None:
            widget = Markdown(
                f"**{display_agent(event.agent)}**\n\n{event.content}",
                classes=f"bubble agent {event.agent}",
            )
            self._streams[key] = (widget, str(event.content))
            await self.mount(widget)
        else:
            widget, current = existing
            current += str(event.content)
            self._streams[key] = (widget, current)
            await widget.update(f"**{display_agent(event.agent)}**\n\n{current}")
        self.scroll_end(animate=False)

    async def add_activity(self, event: AgentEvent) -> None:
        label = display_agent(event.agent)
        if event.kind == EventKind.UPDATE:
            title = event.title or "Research update"
            await self.mount(
                Collapsible(
                    Static(_safe_detail(event.content)),
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
                detail = Static(_safe_detail(event.content))
                self._reasoning[key] = (detail, str(event.content))
                await self.mount(
                    Collapsible(
                        detail,
                        title=f"{label} · reasoning/status",
                        collapsed=False,
                        classes="activity reasoning",
                    )
                )
            else:
                detail, current = existing
                current += str(event.content)
                self._reasoning[key] = (detail, current)
                detail.update(_safe_detail(current))
        elif event.kind == EventKind.TOOL_STARTED:
            title = event.title or "tool"
            widget = Collapsible(
                Static(_safe_detail(event.content), classes="tool-detail"),
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
                    Static(_safe_detail(event.content), classes="tool-detail"),
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
        self.scroll_end(animate=False)

    async def reset_feed(self) -> None:
        await self.remove_children()
        self._streams.clear()
        self._reasoning.clear()
        self._tools.clear()


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
    #prompt {
        dock: bottom;
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
        Binding("f2", "toggle_sidebar", "Agents"),
        Binding("f3", "toggle_files", "Files"),
    ]

    def __init__(self, *, agent: Any | None = None, workspace: Path | None = None) -> None:
        super().__init__()
        self.research_agent = agent
        self.workspace = (workspace or Path.cwd()).resolve()
        self.thread_id = uuid.uuid4().hex
        self._worker: Worker[Any] | None = None
        self._research_running = False
        self._active_agent = ""
        self._started_at = 0.0
        self._animation_index = 0
        self._reduced_motion = bool(os.getenv("NO_COLOR"))
        self._known_files: dict[Path, int] = self._scan_markdown()
        self._session_files: dict[Path, int] = {}

    def compose(self) -> ComposeResult:
        yield Static("MIDAS  ◇  initializing", id="brand")
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("AGENTS", classes="pane-title")
                for agent, label in AGENT_LABELS.items():
                    yield Static(f"○  {label}", id=f"agent-{agent}", classes="agent-row")
                yield Static("TODOS", classes="pane-title")
                yield Static("No todos yet", id="todos")
            with Vertical(id="main"):
                yield ChatTranscript(id="transcript")
                yield Input(
                    placeholder="Ask Midas about a company, sector, or NSE index…",
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

    @work(exclusive=True, group="initialization")
    async def initialize_agent(self) -> None:
        load_dotenv()
        splash = self.query_one("#splash", Static)
        splash.update(f"{_SPLASH_FRAMES[0]}\n\nMIDAS\nWaking the research desk…")
        try:
            if self.research_agent is None:
                from langgraph.checkpoint.memory import InMemorySaver

                from ..deepagents.deepagent import create_midas_agent

                saver = InMemorySaver()
                self.research_agent = await asyncio.to_thread(
                    partial(create_midas_agent, checkpointer=saver)
                )
            missing = [
                name for name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY") if not os.getenv(name)
            ]
            if missing:
                await self.query_one(ChatTranscript).add_system(
                    f"Missing {', '.join(missing)}. Add credentials to .env before starting "
                    "research.",
                    error=True,
                )
            else:
                await self.query_one(ChatTranscript).add_system(
                    "Research desk ready. Context is retained until you use /new or exit."
                )
            self.query_one("#prompt", Input).disabled = False
            self.query_one("#prompt", Input).focus()
            self.query_one("#brand", Static).update("MIDAS  ◆  ready")
        except Exception as exc:
            await self.query_one(ChatTranscript).add_system(
                f"Agent initialization failed: {exc}", error=True
            )
            self.query_one("#brand", Static).update("MIDAS  ✕  initialization failed")
        finally:
            splash.add_class("hidden")

    def _tick_animation(self) -> None:
        if self._reduced_motion:
            if self._research_running:
                agent = display_agent(self._active_agent or "midas-lead-analyst")
                self.query_one("#brand", Static).update(f"MIDAS  …  {agent} working")
            return
        self._animation_index += 1
        splash = self.query_one("#splash", Static)
        if not splash.has_class("hidden"):
            frame = _SPLASH_FRAMES[self._animation_index % len(_SPLASH_FRAMES)]
            splash.update(f"{frame}\n\nMIDAS\nWaking the research desk…")
        if self._research_running:
            spinner = _SPINNER[self._animation_index % len(_SPINNER)]
            elapsed = time.monotonic() - self._started_at
            agent = display_agent(self._active_agent or "midas-lead-analyst")
            self.query_one("#brand", Static).update(
                f"MIDAS  {spinner}  {agent} working  ·  {elapsed:,.0f}s"
            )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value or self._research_running:
            return
        event.input.value = ""
        if value == "/quit":
            self.exit()
            return
        if value == "/new":
            await self._new_session()
            return
        await self.query_one(ChatTranscript).add_user(value)
        self._research_running = True
        self._started_at = time.monotonic()
        self._active_agent = "midas-lead-analyst"
        event.input.disabled = True
        self._set_active_agent(self._active_agent)
        self._worker = self.run_research(value)

    @work(exclusive=True, group="research")
    async def run_research(self, prompt: str) -> None:
        transcript = self.query_one(ChatTranscript)
        try:
            config = {"configurable": {"thread_id": self.thread_id}}
            async for event in stream_agent_events(
                self.research_agent,
                prompt,
                config=config,
            ):
                if event.agent:
                    self._active_agent = event.agent
                    self._set_active_agent(event.agent)
                if event.kind == EventKind.TEXT:
                    await transcript.append_text(event)
                elif event.kind == EventKind.TODOS:
                    self._render_todos(event.content)
                elif event.kind == EventKind.STATUS:
                    continue
                else:
                    await transcript.add_activity(event)
            await transcript.add_system("Turn completed.")
            self.query_one("#brand", Static).update("MIDAS  ◆  ready")
        except asyncio.CancelledError:
            await transcript.add_system("Research cancelled.")
            self.query_one("#brand", Static).update("MIDAS  ◇  cancelled")
        except Exception as exc:
            await transcript.add_system(f"Research failed: {exc}", error=True)
            self.query_one("#brand", Static).update("MIDAS  ✕  failed")
        finally:
            self._research_running = False
            self._set_active_agent("")
            prompt_input = self.query_one("#prompt", Input)
            prompt_input.disabled = False
            prompt_input.focus()

    def _set_active_agent(self, active: str) -> None:
        for agent in AGENT_LABELS:
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
        root = self.workspace / "output" / "research"
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
        tree.reset("output/research")
        root = tree.root
        nodes: dict[tuple[str, ...], TreeNode[Any]] = {(): root}
        leaves: dict[Path, TreeNode[Any]] = {}
        research_root = self.workspace / "output" / "research"
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

    async def _new_session(self) -> None:
        self.thread_id = uuid.uuid4().hex
        self._session_files.clear()
        self._known_files = self._scan_markdown()
        await self.query_one(ChatTranscript).reset_feed()
        await self.query_one(ChatTranscript).add_system("New contextual session started.")
        self._render_todos([])
        self._rebuild_tree()

    def action_new_session(self) -> None:
        if not self._research_running:
            self.run_worker(self._new_session())

    def action_cancel_or_quit(self) -> None:
        if self._research_running and self._worker is not None:
            self._worker.cancel()
        else:
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
    """Launch the interactive Midas terminal interface."""
    MidasApp().run()

"""Normalize LangGraph stream parts into small, UI-friendly events."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..deepagents.telemetry import record_model_usage, record_tool_result


class EventKind(StrEnum):
    """Events understood by the terminal UI."""

    TEXT = "text"
    REASONING = "reasoning"
    UPDATE = "update"
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    TOOL_ERROR = "tool_error"
    TODOS = "todos"
    USAGE = "usage"
    STATUS = "status"


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """One normalized piece of streamed agent activity."""

    kind: EventKind
    agent: str
    content: Any = ""
    event_id: str | None = None
    title: str | None = None


AGENT_LABELS = {
    "midas-lead-analyst": "Lead analyst",
    "research-agent": "Research agent",
    "adversarial-agent": "Adversarial agent",
    "deep-research-agent": "Deep research agent",
    "report-agent": "Report agent",
}


def display_agent(agent: str) -> str:
    """Return the friendly label for an agent identifier."""
    return AGENT_LABELS.get(agent, agent.replace("-", " ").title())


def _agent_for(part: Mapping[str, Any], metadata: Mapping[str, Any] | None = None) -> str:
    if metadata:
        configured = metadata.get("lc_agent_name")
        if isinstance(configured, str) and configured:
            return configured
    namespace = part.get("ns", ())
    if isinstance(namespace, Sequence) and namespace:
        for segment in reversed(namespace):
            candidate = str(segment).split(":", 1)[0]
            if candidate in AGENT_LABELS:
                return candidate
    return "midas-lead-analyst"


def _text_blocks(content: Any) -> tuple[str, str]:
    """Extract provider-visible answer and reasoning/status text."""
    if isinstance(content, str):
        return content, ""
    if not isinstance(content, Sequence):
        return "", ""
    text: list[str] = []
    reasoning: list[str] = []
    for block in content:
        if not isinstance(block, Mapping):
            continue
        block_type = str(block.get("type", "text"))
        value = block.get("text")
        if not isinstance(value, str):
            value = block.get("reasoning")
        if not isinstance(value, str):
            continue
        if "reason" in block_type or block_type in {"thinking", "analysis"}:
            reasoning.append(value)
        elif block_type in {"text", "text-delta", "output_text"}:
            text.append(value)
    return "".join(text), "".join(reasoning)


def _token_usage(message: Any) -> tuple[int, int]:
    """Read token counts from LangChain's normalized or provider metadata."""
    usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, Mapping):
        response = getattr(message, "response_metadata", None)
        if isinstance(response, Mapping):
            usage = response.get("token_usage") or response.get("usage")
    if not isinstance(usage, Mapping):
        return 0, 0

    def count(*names: str) -> int:
        for name in names:
            value = usage.get(name)
            if isinstance(value, int) and not isinstance(value, bool):
                return max(0, value)
        return 0

    return (
        count("input_tokens", "prompt_tokens"),
        count("output_tokens", "completion_tokens"),
    )


async def stream_agent_events(
    research_agent: Any,
    prompt: str,
    *,
    history: Sequence[tuple[str, str]] = (),
    config: Mapping[str, Any] | None = None,
) -> AsyncIterator[AgentEvent]:
    """Run one turn and yield normalized messages, tools, todos, and custom updates."""
    seen_tools: set[str] = set()
    seen_usage: dict[tuple[str, str], tuple[int, int]] = {}
    async for part in research_agent.astream(
        {"messages": [*history, ("user", prompt)]},
        config=config,
        stream_mode=["messages", "updates", "custom"],
        subgraphs=True,
        version="v2",
    ):
        if not isinstance(part, Mapping):
            continue
        mode = part.get("type")
        data = part.get("data")
        if mode == "messages" and isinstance(data, Sequence) and len(data) == 2:
            message, metadata = data
            metadata = metadata if isinstance(metadata, Mapping) else {}
            agent = _agent_for(part, metadata)
            content_blocks = getattr(message, "content_blocks", None)
            source_content = content_blocks or getattr(message, "content", "")
            text, reasoning = _text_blocks(source_content)
            message_id = str(getattr(message, "id", "") or id(message))
            if text:
                yield AgentEvent(EventKind.TEXT, agent, text, message_id)
            if reasoning:
                yield AgentEvent(EventKind.REASONING, agent, reasoning, message_id)
            input_tokens, output_tokens = _token_usage(message)
            usage_key = (agent, message_id)
            previous_input, previous_output = seen_usage.get(usage_key, (0, 0))
            input_delta = max(0, input_tokens - previous_input)
            output_delta = max(0, output_tokens - previous_output)
            if input_delta or output_delta:
                seen_usage[usage_key] = (
                    max(previous_input, input_tokens),
                    max(previous_output, output_tokens),
                )
                try:
                    record_model_usage(
                        agent=agent,
                        call_id=message_id,
                        input_tokens=input_delta,
                        output_tokens=output_delta,
                    )
                except OSError:
                    pass
                yield AgentEvent(
                    EventKind.USAGE,
                    agent,
                    {"input_tokens": input_delta, "output_tokens": output_delta},
                    message_id,
                )
            continue

        agent = _agent_for(part)
        if mode == "custom":
            if isinstance(data, Mapping) and data.get("type") == "deep_agent_update":
                yield AgentEvent(EventKind.UPDATE, agent, str(data.get("update", "")))
            elif data not in (None, ""):
                yield AgentEvent(EventKind.UPDATE, agent, data, title="AI emit")
            continue

        if mode != "updates" or not isinstance(data, Mapping):
            continue
        for node_update in data.values():
            if not isinstance(node_update, Mapping):
                continue
            todos = node_update.get("todos")
            if isinstance(todos, list):
                yield AgentEvent(EventKind.TODOS, agent, todos)
            messages = node_update.get("messages", ())
            if not isinstance(messages, Sequence):
                continue
            for message in messages:
                for call in getattr(message, "tool_calls", ()) or ():
                    if not isinstance(call, Mapping):
                        continue
                    call_id = str(call.get("id", "") or id(call))
                    if call_id in seen_tools:
                        continue
                    seen_tools.add(call_id)
                    name = str(call.get("name", "tool"))
                    args = call.get("args", {})
                    yield AgentEvent(
                        EventKind.TOOL_STARTED,
                        agent,
                        args,
                        call_id,
                        name,
                    )
                tool_call_id = getattr(message, "tool_call_id", None)
                if not tool_call_id:
                    continue
                status = getattr(message, "status", None)
                kind = EventKind.TOOL_ERROR if status == "error" else EventKind.TOOL_FINISHED
                try:
                    record_tool_result(
                        agent=agent,
                        tool=getattr(message, "name", None),
                        call_id=str(tool_call_id),
                        content=getattr(message, "content", ""),
                    )
                except OSError:
                    pass
                yield AgentEvent(
                    kind,
                    agent,
                    getattr(message, "content", ""),
                    str(tool_call_id),
                    getattr(message, "name", None),
                )
    yield AgentEvent(EventKind.STATUS, "midas-lead-analyst", "completed")

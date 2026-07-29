from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from midas.tui.events import EventKind, stream_agent_events


class _StreamingAgent:
    def __init__(self, parts: list[dict[str, Any]]) -> None:
        self.parts = parts
        self.call: dict[str, Any] | None = None

    async def astream(self, payload: Any, **kwargs: Any):
        self.call = {"payload": payload, **kwargs}
        for part in self.parts:
            yield part


class _ProviderBlockChunk:
    """Match providers that leave content empty and stream via content_blocks."""

    id = "provider-message"
    content = ""
    content_blocks = [
        {"type": "reasoning", "reasoning": "Checking evidence"},
        {"type": "text", "text": "Live answer"},
    ]


@pytest.mark.asyncio
async def test_stream_agent_events_normalizes_text_update_todos_and_tools() -> None:
    parts = [
        {
            "type": "messages",
            "ns": ("research-agent:abc",),
            "data": (
                AIMessageChunk(content="Live finding", id="message-1"),
                {"lc_agent_name": "research-agent"},
            ),
        },
        {
            "type": "custom",
            "ns": ("research-agent:abc",),
            "data": {"type": "deep_agent_update", "update": "Checking filings."},
        },
        {
            "type": "updates",
            "ns": ("research-agent:abc",),
            "data": {
                "model": {
                    "todos": [{"content": "Check filings", "status": "in_progress"}],
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "nse_company_filings",
                                    "args": {"symbol": "TCS"},
                                    "id": "call-1",
                                    "type": "tool_call",
                                }
                            ],
                        )
                    ],
                }
            },
        },
        {
            "type": "updates",
            "ns": ("research-agent:abc",),
            "data": {
                "tools": {
                    "messages": [
                        ToolMessage(
                            '{"ok": true}',
                            name="nse_company_filings",
                            tool_call_id="call-1",
                        )
                    ]
                }
            },
        },
    ]
    agent = _StreamingAgent(parts)

    events = [
        event
        async for event in stream_agent_events(
            agent,
            "Research TCS",
            config={"configurable": {"thread_id": "thread-1"}},
        )
    ]

    assert [event.kind for event in events] == [
        EventKind.TEXT,
        EventKind.UPDATE,
        EventKind.TODOS,
        EventKind.TOOL_STARTED,
        EventKind.TOOL_FINISHED,
        EventKind.STATUS,
    ]
    assert all(event.agent == "research-agent" for event in events[:-1])
    assert events[0].content == "Live finding"
    assert events[3].title == "nse_company_filings"
    assert agent.call == {
        "payload": {"messages": [("user", "Research TCS")]},
        "config": {"configurable": {"thread_id": "thread-1"}},
        "stream_mode": ["messages", "updates", "custom"],
        "subgraphs": True,
        "version": "v2",
    }


@pytest.mark.asyncio
async def test_stream_agent_events_exposes_provider_reasoning_and_custom_emit() -> None:
    agent = _StreamingAgent(
        [
            {
                "type": "messages",
                "ns": (),
                "data": (
                    AIMessageChunk(
                        content=[
                            {"type": "reasoning", "reasoning": "Visible status"},
                            {"type": "text", "text": "Answer"},
                        ],
                        id="message-2",
                    ),
                    {"lc_agent_name": "midas-lead-analyst"},
                ),
            },
            {"type": "custom", "ns": (), "data": {"event": "raw emit"}},
        ]
    )

    events = [event async for event in stream_agent_events(agent, "Question")]

    assert [event.kind for event in events] == [
        EventKind.TEXT,
        EventKind.REASONING,
        EventKind.UPDATE,
        EventKind.STATUS,
    ]
    assert events[1].content == "Visible status"
    assert events[2].title == "AI emit"


@pytest.mark.asyncio
async def test_stream_agent_events_reads_provider_content_blocks() -> None:
    agent = _StreamingAgent(
        [
            {
                "type": "messages",
                "ns": (),
                "data": (
                    _ProviderBlockChunk(),
                    {"lc_agent_name": "midas-lead-analyst"},
                ),
            }
        ]
    )

    events = [event async for event in stream_agent_events(agent, "Question")]

    assert [(event.kind, event.content) for event in events[:-1]] == [
        (EventKind.TEXT, "Live answer"),
        (EventKind.REASONING, "Checking evidence"),
    ]

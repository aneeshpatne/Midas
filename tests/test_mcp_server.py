"""Unit tests for the standalone market-info MCP server."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from midas.deepagents import cache as tool_cache
from midas.deepagents.tools import MARKET_INFO_TOOLS
from midas.mcp_server import create_mcp_server


@pytest.fixture(autouse=True)
def disable_external_tool_cache(monkeypatch: pytest.MonkeyPatch):
    tool_cache._memory_cache.clear()
    monkeypatch.setattr("midas.deepagents.cache._get_redis_client", lambda: None)
    yield
    tool_cache._memory_cache.clear()


def _tool_payload_text(call_result: Any) -> str:
    """Normalize FastMCP call_tool return shapes to the JSON text body."""
    if hasattr(call_result, "content"):
        text_parts = [
            block.text
            for block in call_result.content
            if getattr(block, "type", None) == "text" or hasattr(block, "text")
        ]
        return text_parts[0] if text_parts else str(call_result)
    if isinstance(call_result, tuple):
        content = call_result[0]
        return content[0].text if content else ""
    if isinstance(call_result, list) and call_result:
        first = call_result[0]
        return first.text if hasattr(first, "text") else str(first)
    return str(call_result)


def test_market_info_tools_exclude_web_and_agent_helpers() -> None:
    names = {tool.name for tool in MARKET_INFO_TOOLS}
    assert "web_research" not in names
    assert "twitter_search" not in names
    assert "send_update" not in names
    assert "generate_bar_chart" not in names
    # Core scrape / market tools must be present.
    assert {
        "company_fundamentals",
        "earnings_transcripts",
        "market_signals",
        "nse_list_index",
        "nse_equity_snapshot",
        "india_market_context",
    } <= names


def test_create_mcp_server_registers_market_tools() -> None:
    server = create_mcp_server()
    registered = set(server._tool_manager._tools)  # noqa: SLF001 — FastMCP private map
    expected = {tool.name for tool in MARKET_INFO_TOOLS}
    assert registered == expected
    assert server.name == "equity-data"


@pytest.mark.asyncio
async def test_mcp_tool_list_matches_market_info_tools() -> None:
    """Exercise the FastMCP list_tools path used by MCP hosts."""
    server = create_mcp_server()
    tools = await server.list_tools()
    names = {tool.name for tool in tools}
    assert names == {tool.name for tool in MARKET_INFO_TOOLS}
    fundamentals = next(tool for tool in tools if tool.name == "company_fundamentals")
    assert fundamentals.description
    assert "Tickertape" not in (fundamentals.description or "")
    assert "https://" not in (fundamentals.description or "")
    assert "RELIANCE" not in (fundamentals.description or "")
    props = (fundamentals.inputSchema or {}).get("properties", {})
    # Prefer real arg schema; tolerate wrapper edge cases but never empty.
    assert props, "MCP tool must expose an input schema"
    assert "symbol" in props or "args" in props


@pytest.mark.asyncio
async def test_mcp_company_fundamentals_call_uses_underlying_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from midas.deepagents import tools as tools_mod
    from midas.fundamentals.models import (
        CompanyPage,
        CompanyProfile,
        ReportingBasis,
        CompanyFundamentalsResult,
    )

    page = CompanyPage(
        url="https://example.com/fundamentals/company/TCS/",
        symbol="TCS",
        basis=ReportingBasis.STANDALONE,
        profile=CompanyProfile(name="Tata Consultancy Services Ltd", symbol="TCS"),
    )
    result = CompanyFundamentalsResult(
        symbol="TCS",
        requested_basis=ReportingBasis.STANDALONE,
        page=page,
        scraped_at="2026-07-28T00:00:00+00:00",
        source_urls=(page.url,),
    )

    async def fake_scrape(symbol: str, **kwargs: Any) -> CompanyFundamentalsResult:
        assert symbol == "TCS"
        assert kwargs.get("include_concalls") is False
        return result

    monkeypatch.setattr(tools_mod, "scrape_company", fake_scrape)

    server = create_mcp_server()
    call_result = await server.call_tool("company_fundamentals", {"symbol": "TCS"})
    text = _tool_payload_text(call_result)
    payload = json.loads(text)
    assert payload["ok"] is True
    assert payload["symbol"] == "TCS"
    assert "source_urls" not in payload
    assert "https://" not in text
    assert "example.com" not in text


@pytest.mark.asyncio
async def test_mcp_rejects_overlapping_market_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sequential market gate: second concurrent call returns busy immediately."""
    from midas.deepagents import tools as tools_mod
    from midas.fundamentals.models import (
        CompanyPage,
        CompanyProfile,
        ReportingBasis,
        CompanyFundamentalsResult,
    )

    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_scrape(symbol: str, **kwargs: Any) -> CompanyFundamentalsResult:
        started.set()
        await release.wait()
        page = CompanyPage(
            url=f"https://example.com/fundamentals/company/{symbol}/",
            symbol=symbol,
            basis=ReportingBasis.STANDALONE,
            profile=CompanyProfile(name=symbol, symbol=symbol),
        )
        return CompanyFundamentalsResult(
            symbol=symbol,
            requested_basis=ReportingBasis.STANDALONE,
            page=page,
            scraped_at="2026-07-28T00:00:00+00:00",
            source_urls=(page.url,),
        )

    monkeypatch.setattr(tools_mod, "scrape_company", slow_scrape)
    monkeypatch.setattr(
        tools_mod,
        "fetch_nse_equity_snapshot",
        lambda symbol: {"symbol": symbol, "last_price": 1.0},
    )

    server = create_mcp_server()
    first = asyncio.create_task(server.call_tool("company_fundamentals", {"symbol": "TCS"}))
    await started.wait()

    # Same source while fundamentals is active.
    same_source = json.loads(
        _tool_payload_text(await server.call_tool("earnings_transcripts", {"symbol": "INFY"}))
    )
    # Different source while any market tool is active (MCP sequential policy).
    cross_source = json.loads(
        _tool_payload_text(await server.call_tool("nse_equity_snapshot", {"symbol": "TCS"}))
    )

    release.set()
    first_payload = json.loads(_tool_payload_text(await first))

    assert first_payload["ok"] is True
    assert same_source["ok"] is False
    assert same_source["status"] == "busy"
    assert same_source["retryable"] is True
    assert cross_source["ok"] is False
    assert cross_source["status"] == "busy"
    assert cross_source["retryable"] is True
    assert cross_source["source"] == "market"

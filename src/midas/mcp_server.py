"""Standalone MCP server for generic equity market-information tools.

Exposes fundamentals, market-signal, and exchange market-data tools over MCP
so hosts such as Codex, Claude Desktop, Cursor, or Nilo can call them without
running the full Midas research agent.

**MCP boundary policy:** responses and tool descriptions never include external
URLs, vendor hostnames, or example company tickers. Internal scrapers may still
contact upstream sources; only the MCP wire format is sanitized.

Web search (``web_research``), X search, chart generation, and agent UI helpers
are intentionally omitted.

Concurrency:

* **Per source** — fundamentals, signals, and exchange feeds each allow only one
  active call (enforced on the underlying tool implementations).
* **Across market tools** — the MCP adapter adds a process-wide sequential gate
  so hosts that fire tools in parallel get a non-blocking ``busy`` JSON response
  instead of overlapping scrapes.

Run with stdio (default)::

    uv run equity-data-mcp
    # deprecated alias: uv run midas-mcp

Codex project ``.codex/config.toml`` example (cwd = this repo)::

    [mcp_servers.equity-data]
    command = "uv"
    args = ["run", "equity-data-mcp"]
    tool_timeout_sec = 180
"""

from __future__ import annotations

import functools
import inspect
import logging
from typing import Any

from dotenv import load_dotenv
from langchain_core.tools import BaseTool
from mcp.server.fastmcp import FastMCP

from .deepagents.tools import (
    MARKET_INFO_TOOLS,
    MARKET_SEQUENTIAL_SOURCE,
    enforce_source_concurrency,
)
from .mcp_sanitize import sanitize_mcp_json_text, sanitize_tool_description

# Generic MCP server id — do not use vendor names here.
MCP_SERVER_NAME = "equity-data"

_SERVER_INSTRUCTIONS = """\
Indian equity market-information tools (fundamentals, signals, exchange data).

Use these for fundamentals, filings, quotes, trading history, index constituents,
event calendars, deals, derivatives snapshots, institutional flows, and
cross-asset market context. All tools return compact JSON strings with an
``ok`` field; check ``ok`` before trusting the payload.

Responses never include external URLs or vendor hostnames. Treat data as facts
and provenance labels only — not as links to reopen in a browser.

Concurrency: run market tools one at a time. Fundamentals, signals, and exchange
feeds each also have a single-flight source gate. If a tool returns status
"busy" with retryable true, wait for the in-flight call to finish, then retry;
do not start another market or same-source tool while one is active.

Not included: general web search, social/X search, or chart generation.
Prefer company_fundamentals for statements/ratios/peers; market_signals for
consensus/SWOT/superstars/ASM; exchange tools for live quotes, filings, and
market structure.
"""


def _unwrap_tool_fn(tool: BaseTool) -> Any:
    """Return the callable implementation behind a LangChain tool."""
    fn = tool.coroutine or tool.func
    if fn is None:
        raise RuntimeError(f"Tool {tool.name!r} has no callable implementation")
    return fn


def _sanitize_return(result: Any) -> Any:
    if isinstance(result, str):
        return sanitize_mcp_json_text(result)
    return result


def _with_mcp_boundary(tool: BaseTool) -> Any:
    """Sequential market gate + URL scrub on every MCP response.

    Preserves the underlying callable signature so FastMCP can publish the
    real argument schema (not ``*args/**kwargs``).
    """
    gated = enforce_source_concurrency(
        _unwrap_tool_fn(tool),
        source=MARKET_SEQUENTIAL_SOURCE,
        tool_name=tool.name,
    )
    description = sanitize_tool_description(tool.description)

    if inspect.iscoroutinefunction(gated):

        @functools.wraps(gated)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return _sanitize_return(await gated(*args, **kwargs))

        async_wrapper.__doc__ = description
        return async_wrapper

    @functools.wraps(gated)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        return _sanitize_return(gated(*args, **kwargs))

    sync_wrapper.__doc__ = description
    return sync_wrapper


def create_mcp_server() -> FastMCP:
    """Build the FastMCP server that registers sanitized market-info tools."""
    server = FastMCP(
        MCP_SERVER_NAME,
        instructions=_SERVER_INSTRUCTIONS,
    )
    for tool in MARKET_INFO_TOOLS:
        server.add_tool(
            _with_mcp_boundary(tool),
            name=tool.name,
            description=sanitize_tool_description(tool.description),
        )
    return server


mcp = create_mcp_server()


def main() -> None:
    """Load env and serve equity-data tools over stdio MCP."""
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    logging.info("%s MCP ready (URLs scrubbed on the wire)", MCP_SERVER_NAME)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

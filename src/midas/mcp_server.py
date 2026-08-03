"""Standalone MCP server for Midas market-info scrape tools.

Exposes company fundamentals, market-signal, and NSE market-data tools over the Model Context
Protocol so hosts such as Codex, Claude Desktop, or Cursor can call them without
running the full Midas research agent.

Web search (``web_research``), X search, chart generation, and agent UI helpers
are intentionally omitted.

Concurrency matches the in-app research tools:

* **Per source** — fundamentals, signals, and NSE each allow only one active call
  (already enforced on the underlying tool implementations).
* **Across market tools** — the MCP adapter adds a process-wide sequential gate
  so hosts that fire tools in parallel get a non-blocking ``busy`` JSON response
  instead of overlapping scrapes.

Run with stdio (default, for Codex / Claude Desktop)::

    uv run midas-mcp
    # or: python -m midas.mcp_server

Codex ``~/.codex/config.toml`` example::

    [mcp_servers.midas]
    command = "uv"
    args = ["run", "--directory", "/absolute/path/to/Midas", "midas-mcp"]
    tool_timeout_sec = 180
"""

from __future__ import annotations

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

_SERVER_INSTRUCTIONS = """\
Indian equity market-information tools from Midas (fundamentals, signals, NSE).

Use these for fundamentals, filings, quotes, trading history, index constituents,
event calendars, deals, derivatives snapshots, institutional flows, and
cross-asset market context. All tools return compact JSON strings with an
``ok`` field; check ``ok`` before trusting the payload.

Concurrency: run market tools one at a time. Fundamentals, signals, and NSE each
also have a single-flight source gate. If a tool returns status "busy" with
retryable true, wait for the in-flight call to finish, then retry; do not start
another market or same-source tool while one is active.

Not included: general web search, social/X search, or chart generation.
Prefer company_fundamentals for statements/ratios/peers; market_signals for consensus/SWOT/
superstars/ASM; NSE tools for live quotes, filings, and market structure.
"""


def _unwrap_tool_fn(tool: BaseTool) -> Any:
    """Return the callable implementation behind a LangChain tool.

    The returned callable already includes Redis caching and the per-source
    single-flight gate applied in ``deepagents.tools``.
    """
    fn = tool.coroutine or tool.func
    if fn is None:
        raise RuntimeError(f"Tool {tool.name!r} has no callable implementation")
    return fn


def _with_mcp_concurrency(tool: BaseTool) -> Any:
    """Preserve per-source gates and enforce sequential market-tool execution.

    External hosts often issue parallel tool calls. Agents are prompted to run
    market tools sequentially; MCP hosts are not, so we hard-enforce a process-
    wide single-flight slot for the whole market-info set while keeping the
    underlying per-source gates intact.
    """
    return enforce_source_concurrency(
        _unwrap_tool_fn(tool),
        source=MARKET_SEQUENTIAL_SOURCE,
        tool_name=tool.name,
    )


def create_mcp_server() -> FastMCP:
    """Build the FastMCP server that registers all market-info tools."""
    server = FastMCP(
        "midas-market",
        instructions=_SERVER_INSTRUCTIONS,
    )
    for tool in MARKET_INFO_TOOLS:
        server.add_tool(
            _with_mcp_concurrency(tool),
            name=tool.name,
            description=tool.description,
        )
    return server


mcp = create_mcp_server()


def main() -> None:
    """Load env and serve market-info tools over stdio MCP."""
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # Hosts (Codex, Claude Desktop, Cursor) spawn this process and speak MCP over stdin/stdout.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

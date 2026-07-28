"""Agent-safe wrappers around Midas research capabilities.

Each tool returns compact JSON so a DeepAgent can cite the source URL and decide
which follow-up lookup to make without receiving the full raw scraper payload.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from ..pipeline import MidasError, search_and_scrape
from ..fundamentals import FundamentalsError, scrape_company
from ..signals import signals providerError, scrape_signals


def _json(data: dict[str, Any]) -> str:
    """Serialize tool output consistently for model consumption."""
    return json.dumps(data, ensure_ascii=False, default=str)


@tool("web_research")
async def web_research(query: str, max_results: int = 5) -> str:
    """Search the public web and summarize only the pages Midas successfully scraped.

    Use for recent news, events, or facts not available in Screener. The result
    includes a grounded summary plus source URLs and scrape statuses.

    Args:
        query: Precise web-search query.
        max_results: Number of pages to scrape, from 1 to 10 (default 5).
    """
    try:
        result = await search_and_scrape(query, max_results=max_results)
    except (MidasError, ValueError) as exc:
        return _json({"ok": False, "error": str(exc)})

    return _json(
        {
            "ok": True,
            "query": result.query,
            "summary": result.compressed,
            "sources": [
                {
                    "id": source.source_id,
                    "title": source.title,
                    "url": source.url,
                    "status": source.status.value,
                    "error": source.error,
                }
                for source in result.sources
            ],
        }
    )


@tool("company_fundamentals")
async def company_fundamentals(symbol: str, consolidated: bool = False) -> str:
    """Fetch normal fundamentals provider company fundamentals and market data for an NSE symbol.

    Use for financial statements, ratios, peers, shareholding, company profile, and
    announcements. This intentionally does not download earnings-call transcripts;
    use ``earnings_transcripts`` when the user needs management commentary.

    Args:
        symbol: NSE/Screener trading symbol, for example RELIANCE, TCS, or INFY.
        consolidated: Whether to request consolidated rather than standalone figures.
    """
    try:
        result = await scrape_company(
            symbol,
            consolidated=consolidated,
            include_peers=True,
            include_chart=True,
            include_concalls=False,
        )
    except (FundamentalsError, ValueError) as exc:
        return _json({"ok": False, "symbol": symbol, "error": str(exc)})

    payload = result.agent_payload()
    # The markdown brief is more token-efficient and contains the useful snapshot.
    return _json(
        {
            "ok": True,
            "symbol": result.symbol,
            "source_urls": list(result.source_urls),
            "brief": payload["agent_brief_markdown"],
            "data": {key: value for key, value in payload.items() if key != "agent_brief_markdown"},
        }
    )


@tool("earnings_transcripts")
async def earnings_transcripts(
    symbol: str,
    consolidated: bool = False,
    limit: int = 2,
    summarize: bool = True,
) -> str:
    """Download and extract recent Screener-linked earnings-call transcripts.

    Use this separately from normal company research when the question needs
    management guidance, demand commentary, margins, capex, risks, or Q&A.

    Args:
        symbol: NSE/Screener trading symbol, for example RELIANCE, TCS, or INFY.
        consolidated: Whether to use the consolidated company page for concall links.
        limit: Number of latest unique transcript PDFs to process, from 1 to 5.
        summarize: Summarize extracted PDFs with the configured Ollama model.
    """
    if not 1 <= limit <= 5:
        return _json({"ok": False, "symbol": symbol, "error": "limit must be between 1 and 5"})

    try:
        result = await scrape_company(
            symbol,
            consolidated=consolidated,
            include_peers=False,
            include_chart=False,
            include_concalls=True,
            summarize_concalls=summarize,
            concall_limit=limit,
        )
    except (FundamentalsError, ValueError) as exc:
        return _json({"ok": False, "symbol": symbol, "error": str(exc)})

    transcripts = result.page.concall_transcripts
    return _json(
        {
            "ok": True,
            "symbol": result.symbol,
            "company": result.page.profile.name,
            "source_url": result.page.url,
            "transcripts": [transcript.model_dump(mode="json") for transcript in transcripts],
            "available_concall_links": [
                {"date_label": call.date_label, "transcript_url": call.transcript_url}
                for call in result.page.concalls
                if call.transcript_url
            ],
        }
    )


@tool("market_signals")
async def market_signals(symbol: str) -> str:
    """Fetch high-impact free signals provider signals that Screener does not cover well.

    Use after or alongside ``company_fundamentals`` for:
    - analyst consensus price target (headline)
    - SWOT rule-based strengths / weaknesses / opportunities / threats
    - superstar (ace investor) holdings / recent buys / sells
    - ASM/GSM surveillance risk flag
    - latest FII/DII cash-segment flow snapshot

    Do not use this as a replacement for Screener fundamentals (statements,
    ratios, peers, concalls). Prefer Screener for those.

    Args:
        symbol: NSE trading symbol, for example TCS, TITAN, or INFY.
    """
    try:
        result = await scrape_signals(symbol)
    except (signals providerError, ValueError) as exc:
        return _json({"ok": False, "symbol": symbol, "error": str(exc)})

    return _json(
        {
            "ok": True,
            "symbol": result.symbol,
            "source_urls": list(result.source_urls),
            "brief": result.agent_brief(),
            "data": result.agent_payload(),
        }
    )


MIDAS_TOOLS = (web_research, company_fundamentals, earnings_transcripts, market_signals)


"""Agent-safe wrappers around Midas research capabilities.

Each tool returns compact JSON so a DeepAgent can cite the source URL and decide
which follow-up lookup to make without receiving the full raw scraper payload.
"""

from __future__ import annotations

import inspect
import json
import logging
import shutil
import subprocess
import tempfile
import threading
from datetime import date
from enum import StrEnum
from functools import wraps
from typing import Annotated, Any

from langchain_core.tools import BaseTool, tool
from langgraph.config import get_stream_writer
from pydantic import Field

from ..market_data import (
    fetch_equity_event_calendar,
    fetch_equity_trading_history,
    fetch_exchange_deals,
    fetch_india_market_context,
    fetch_institutional_activity,
    fetch_nse_company_filings,
    fetch_nse_derivatives_snapshot,
    fetch_nse_equity_snapshot,
    fetch_nse_market_scan,
)
from ..pipeline import MidasError, search_and_scrape
from ..fundamentals import FundamentalsError, scrape_company
from ..signals import signals providerError, scrape_signals
from .cache import redis_cached_tool
from .charts import (  # noqa: F401
    CHART_TOOLS,
    ChartDatum,
    ChartSeries,
    HeatmapCell,
    ScatterPoint,
    generate_area_chart,
    generate_bar_chart,
    generate_heatmap_chart,
    generate_horizontal_bar_chart,
    generate_line_chart,
    generate_pie_chart,
    generate_scatter_chart,
    generate_stacked_bar_chart,
)

TWITTER_SEARCH_MAX_CALLS = 2
"""Default maximum number of Grok/X searches available to one agent."""

_TWITTER_SEARCH_TIMEOUT_S = 60
_CACHE_TTL_LIVE_SECONDS = 5 * 60
_CACHE_TTL_MARKET_SECONDS = 60 * 60
_CACHE_TTL_WEB_SECONDS = 6 * 60 * 60
_CACHE_TTL_COMPANY_SECONDS = 24 * 60 * 60
_CACHE_TTL_TRANSCRIPT_SECONDS = 7 * 24 * 60 * 60

_NSE_EQUITY_MARKET_URL = "https://www.nseindia.com/market-data/live-equity-market"

_MARKET_TOOL_ERRORS = (
    OSError,
    TimeoutError,
    ConnectionError,
    ImportError,
    ValueError,
    RuntimeError,
    KeyError,
    TypeError,
)

ai_log = logging.getLogger(__name__)

_SOURCE_WEB = "web"
_SOURCE_FUNDAMENTALS = "screener"
_SOURCE_SIGNALS = "trendlyne"
_SOURCE_NSE = "nse"
_SOURCE_X = "x"


class _SourceConcurrencyGate:
    """Allow at most one active agent tool call per upstream source."""

    def __init__(self) -> None:
        self._active: set[str] = set()
        self._lock = threading.Lock()

    def try_acquire(self, source: str) -> bool:
        """Reserve ``source`` without waiting; return whether it was reserved."""
        with self._lock:
            if source in self._active:
                return False
            self._active.add(source)
            return True

    def release(self, source: str) -> None:
        """Release a previously reserved source."""
        with self._lock:
            self._active.discard(source)


_SOURCE_GATE = _SourceConcurrencyGate()


def _source_busy_response(source: str, tool_name: str) -> str:
    """Tell the agent that a same-source call is still running."""
    return _json(
        {
            "ok": False,
            "status": "busy",
            "retryable": True,
            "source": source,
            "tool": tool_name,
            "message": (
                f"Another {source} tool is already running. Wait for it to finish, "
                f"then retry {tool_name}; do not start another {source} tool while "
                "it is busy."
            ),
        }
    )


def _source_limited(source: str, tool_name: str):
    """Decorate sync or async tools with a non-blocking source gate."""

    def decorator(function):
        if inspect.iscoroutinefunction(function):

            @wraps(function)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not _SOURCE_GATE.try_acquire(source):
                    return _source_busy_response(source, tool_name)
                try:
                    return await function(*args, **kwargs)
                finally:
                    _SOURCE_GATE.release(source)

            return async_wrapper

        @wraps(function)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _SOURCE_GATE.try_acquire(source):
                return _source_busy_response(source, tool_name)
            try:
                return function(*args, **kwargs)
            finally:
                _SOURCE_GATE.release(source)

        return sync_wrapper

    return decorator


def enforce_source_concurrency(function, *, source: str, tool_name: str):
    """Apply the shared single-flight source gate to a callable.

    Used by the agent tool decorators and by the MCP server so external hosts
    get the same non-blocking ``busy`` response when a source is already active.
    """
    return _source_limited(source, tool_name)(function)


class NseIndex(StrEnum):
    """Allowed NSE index names for ``nse_list_index`` (NseIndiaApi).

    Values match ``NSE.listEquityStocksByIndex`` after uppercasing.
    """

    NIFTY_50 = "NIFTY 50"
    NIFTY_BANK = "NIFTY BANK"
    NIFTY_FIN_SERVICE = "NIFTY FIN SERVICE"
    NIFTY_MID_SELECT = "NIFTY MID SELECT"
    NIFTY_NEXT_50 = "NIFTY NEXT 50"
    NIFTY_100 = "NIFTY 100"
    NIFTY_200 = "NIFTY 200"
    NIFTY_500 = "NIFTY 500"
    NIFTY_FPI_150 = "NIFTY FPI 150"
    NIFTY_LARGEMID250 = "NIFTY LARGEMID250"
    NIFTY_MICROCAP250 = "NIFTY MICROCAP250"
    NIFTY_MIDCAP_100 = "NIFTY MIDCAP 100"
    NIFTY_MIDCAP_150 = "NIFTY MIDCAP 150"
    NIFTY_MIDCAP_50 = "NIFTY MIDCAP 50"
    NIFTY_MIDSMALL_50_50 = "NIFTY MIDSMALL 50 50"
    NIFTY_MIDSML_400 = "NIFTY MIDSML 400"
    NIFTY_SMALLCAP_500 = "NIFTY SMALLCAP 500"
    NIFTY_SMLCAP_100 = "NIFTY SMLCAP 100"
    NIFTY_SMLCAP_250 = "NIFTY SMLCAP 250"
    NIFTY_SMLCAP_50 = "NIFTY SMLCAP 50"
    NIFTY_TOTAL_MKT = "NIFTY TOTAL MKT"
    NIFTY500_LMS_EQL = "NIFTY500 LMS EQL"
    NIFTY500_MULTICAP = "NIFTY500 MULTICAP"
    NIFTY_AUTO = "NIFTY AUTO"
    NIFTY_CEMENT = "NIFTY CEMENT"
    NIFTY_CHEMICALS = "NIFTY CHEMICALS"
    NIFTY_CONSR_DURBL = "NIFTY CONSR DURBL"
    NIFTY_FINSEREXBNK = "NIFTY FINSEREXBNK"
    NIFTY_FINSRV25_50 = "NIFTY FINSRV25 50"
    NIFTY_FMCG = "NIFTY FMCG"
    NIFTY_HEALTHCARE = "NIFTY HEALTHCARE"
    NIFTY_IT = "NIFTY IT"
    NIFTY_MEDIA = "NIFTY MEDIA"
    NIFTY_METAL = "NIFTY METAL"
    NIFTY_MIDSML_HLTH = "NIFTY MIDSML HLTH"
    NIFTY_MS_FIN_SERV = "NIFTY MS FIN SERV"
    NIFTY_MS_IT_TELCM = "NIFTY MS IT TELCM"
    NIFTY_OIL_AND_GAS = "NIFTY OIL AND GAS"
    NIFTY_PHARMA = "NIFTY PHARMA"
    NIFTY_PSU_BANK = "NIFTY PSU BANK"
    NIFTY_PVT_BANK = "NIFTY PVT BANK"
    NIFTY_REALTY = "NIFTY REALTY"
    NIFTY_REITS_REALTY = "NIFTY REITS REALTY"
    NIFTY500_HEALTH = "NIFTY500 HEALTH"
    NIFTY_CAPITAL_MKT = "NIFTY CAPITAL MKT"
    NIFTY_COMMODITIES = "NIFTY COMMODITIES"
    NIFTY_CONSUMPTION = "NIFTY CONSUMPTION"
    NIFTY_COREHOUSING = "NIFTY COREHOUSING"
    NIFTY_CORP_MAATR = "NIFTY CORP MAATR"
    NIFTY_CPSE = "NIFTY CPSE"
    NIFTY_ENERGY = "NIFTY ENERGY"
    NIFTY_EV = "NIFTY EV"
    NIFTY_HOUSING = "NIFTY HOUSING"
    NIFTY_IND_DEFENCE = "NIFTY IND DEFENCE"
    NIFTY_IND_DIGITAL = "NIFTY IND DIGITAL"
    NIFTY_IND_TOURISM = "NIFTY IND TOURISM"
    NIFTY_INDIA_MFG = "NIFTY INDIA MFG"
    NIFTY_INFRA = "NIFTY INFRA"
    NIFTY_INFRALOG = "NIFTY INFRALOG"
    NIFTY_INTERNET = "NIFTY INTERNET"
    NIFTY_IPO = "NIFTY IPO"
    NIFTY_MID_LIQ_15 = "NIFTY MID LIQ 15"
    NIFTY_MNC = "NIFTY MNC"
    NIFTY_MOBILITY = "NIFTY MOBILITY"
    NIFTY_MS_IND_CONS = "NIFTY MS IND CONS"
    NIFTY_MULTI_INFRA = "NIFTY MULTI INFRA"
    NIFTY_MULTI_MFG = "NIFTY MULTI MFG"
    NIFTY_NEW_CONSUMP = "NIFTY NEW CONSUMP"
    NIFTY_NONCYC_CONS = "NIFTY NONCYC CONS"
    NIFTY_PSE = "NIFTY PSE"
    NIFTY_RAILWAYSPSU = "NIFTY RAILWAYSPSU"
    NIFTY_RURAL = "NIFTY RURAL"
    NIFTY_SERV_SECTOR = "NIFTY SERV SECTOR"
    NIFTY_SHARIAH_25 = "NIFTY SHARIAH 25"
    NIFTY_SME_EMERGE = "NIFTY SME EMERGE"
    NIFTY_TATA_25_CAP = "NIFTY TATA 25 CAP"
    NIFTY_TRANS_LOGIS = "NIFTY TRANS LOGIS"
    NIFTY_WAVES = "NIFTY WAVES"
    NIFTY100_ENH_ESG = "NIFTY100 ENH ESG"
    NIFTY100_ESG = "NIFTY100 ESG"
    NIFTY100_LIQ_15 = "NIFTY100 LIQ 15"
    NIFTY50_SHARIAH = "NIFTY50 SHARIAH"
    NIFTY500_SHARIAH = "NIFTY500 SHARIAH"
    NIFTYCONGLOMERATE = "NIFTYCONGLOMERATE"
    NIFTY_ALPHA_50 = "NIFTY ALPHA 50"
    NIFTY_ALPHALOWVOL = "NIFTY ALPHALOWVOL"
    NIFTY_AQL_30 = "NIFTY AQL 30"
    NIFTY_AQLV_30 = "NIFTY AQLV 30"
    NIFTY_DIV_OPPS_50 = "NIFTY DIV OPPS 50"
    NIFTY_GROWSECT_15 = "NIFTY GROWSECT 15"
    NIFTY_HIGHBETA_50 = "NIFTY HIGHBETA 50"
    NIFTY_LOW_VOL_50 = "NIFTY LOW VOL 50"
    NIFTY_M150_QLTY50 = "NIFTY M150 QLTY50"
    NIFTY_MULTI_MQ_50 = "NIFTY MULTI MQ 50"
    NIFTY_QLTY_LV_30 = "NIFTY QLTY LV 30"
    NIFTY_SML250_Q50 = "NIFTY SML250 Q50"
    NIFTY_TMMQ_50 = "NIFTY TMMQ 50"
    NIFTY_TOP_10_EW = "NIFTY TOP 10 EW"
    NIFTY_TOP_15_EW = "NIFTY TOP 15 EW"
    NIFTY_TOP_20_EW = "NIFTY TOP 20 EW"
    NIFTY100_ALPHA_30 = "NIFTY100 ALPHA 30"
    NIFTY100_EQL_WGT = "NIFTY100 EQL WGT"
    NIFTY100_LOWVOL30 = "NIFTY100 LOWVOL30"
    NIFTY100_QUALTY30 = "NIFTY100 QUALTY30"
    NIFTY200_ALPHA_30 = "NIFTY200 ALPHA 30"
    NIFTY200_QUALTY30 = "NIFTY200 QUALTY30"
    NIFTY200_VALUE_30 = "NIFTY200 VALUE 30"
    NIFTY200MOMENTM30 = "NIFTY200MOMENTM30"
    NIFTY50_EQL_WGT = "NIFTY50 EQL WGT"
    NIFTY50_VALUE_20 = "NIFTY50 VALUE 20"
    NIFTY500_EW = "NIFTY500 EW"
    NIFTY500_FLEXICAP = "NIFTY500 FLEXICAP"
    NIFTY500_LOWVOL50 = "NIFTY500 LOWVOL50"
    NIFTY500_MQVLV50 = "NIFTY500 MQVLV50"
    NIFTY500_QLTY50 = "NIFTY500 QLTY50"
    NIFTY500_VALUE_50 = "NIFTY500 VALUE 50"
    NIFTY500MOMENTM50 = "NIFTY500MOMENTM50"
    NIFTYM150MOMNTM50 = "NIFTYM150MOMNTM50"
    NIFTYMS400_MQ_100 = "NIFTYMS400 MQ 100"
    NIFTYSML250MQ_100 = "NIFTYSML250MQ 100"
    PERMITTED_TO_TRADE = "PERMITTED TO TRADE"
    SECURITIES_IN_F_AND_O = "SECURITIES IN F&O"


class MarketContextIndex(StrEnum):
    """High-value Nifty benchmarks supported by ``india_market_context``."""

    NIFTY_50 = "NIFTY 50"
    NIFTY_BANK = "NIFTY BANK"
    NIFTY_IT = "NIFTY IT"
    NIFTY_AUTO = "NIFTY AUTO"
    NIFTY_METAL = "NIFTY METAL"
    NIFTY_PHARMA = "NIFTY PHARMA"
    NIFTY_ENERGY = "NIFTY ENERGY"
    NIFTY_OIL_AND_GAS = "NIFTY OIL AND GAS"


class McxCommodity(StrEnum):
    """Research-relevant MCX spot commodities supported by the context tool."""

    CRUDEOIL = "CRUDEOIL"
    GOLD = "GOLD"
    SILVER = "SILVER"
    COPPER = "COPPER"
    ALUMINIUM = "ALUMINIUM"
    ZINC = "ZINC"
    NATURALGAS = "NATURALGAS"


class DealType(StrEnum):
    """Exchange-reported transaction categories supported by ``exchange_deals``."""

    BULK = "bulk"
    BLOCK = "block"
    SHORT = "short"


def _json(data: dict[str, Any]) -> str:
    """Serialize tool output consistently for model consumption."""
    return json.dumps(data, ensure_ascii=False, default=str)


def _compact_index_row(row: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields useful for listing index members."""
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    return {
        "symbol": row.get("symbol"),
        "company_name": meta.get("companyName") or meta.get("company_name"),
        "series": row.get("series"),
        "last_price": row.get("lastPrice"),
        "p_change": row.get("pChange"),
        "total_traded_volume": row.get("totalTradedVolume"),
    }


def _fetch_nse_index_list(index: NseIndex) -> dict[str, Any]:
    """Call NseIndiaApi for live equity constituents of ``index``."""
    from nse import NSE

    with tempfile.TemporaryDirectory(prefix="midas-nse-") as tmp:
        with NSE(download_folder=tmp, server=True) as client:
            return client.listEquityStocksByIndex(index=index.value)


@tool("send_update")
def send_update(
    update: Annotated[
        str,
        Field(
            min_length=1,
            description=(
                "A talkative, multi-sentence progress update for the user. Write like "
                "you are narrating the research out loud: context, intent, findings, "
                "uncertainty, and next steps. Prefer several full sentences (often a "
                "short paragraph) over a terse one-liner."
            ),
        ),
    ],
) -> str:
    """Show a conversational progress update to the user during long-running research.

    Call this regularly while working so the user can follow the research in real
    time. Include what you are doing, why, what you found, uncertainty, and what
    comes next. Do not use it for the final answer.
    """
    try:
        # LangGraph flushes custom stream chunks as soon as the tool emits them.
        # The fallback keeps direct unit-test/tool invocation usable outside a graph.
        get_stream_writer()({"type": "deep_agent_update", "update": update})
    except RuntimeError:
        pass
    return "Progress update displayed successfully."


def _run_twitter_search(query: str) -> str:
    """Call the Grok CLI for the latest X/Twitter information about ``query``."""
    grok = shutil.which("grok")
    if not grok:
        raise RuntimeError("grok CLI not found on PATH; install it to use twitter_search")

    completed = subprocess.run(
        [grok, "-p", f"{query} get me latest information on X about this"],
        capture_output=True,
        text=True,
        timeout=_TWITTER_SEARCH_TIMEOUT_S,
        check=False,
    )
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if completed.returncode != 0:
        detail = stderr or stdout or "no output"
        raise RuntimeError(f"grok exited with code {completed.returncode}: {detail}")
    if not stdout:
        if stderr:
            return stderr
        raise RuntimeError("grok returned empty output")
    return stdout


class _TwitterSearchBudget:
    """Thread-safe call budget shared across a single tool instance."""

    def __init__(self, max_calls: int = TWITTER_SEARCH_MAX_CALLS) -> None:
        if max_calls < 1:
            raise ValueError("max_calls must be >= 1")
        self.max_calls = max_calls
        self._used = 0
        self._lock = threading.Lock()

    def try_acquire(self) -> tuple[bool, int, int]:
        """Reserve one call and return ``(ok, used_after, max_calls)``."""
        with self._lock:
            if self._used >= self.max_calls:
                return False, self._used, self.max_calls
            self._used += 1
            return True, self._used, self.max_calls


def build_twitter_search_tool(max_calls: int = TWITTER_SEARCH_MAX_CALLS) -> BaseTool:
    """Build a Grok-backed X search tool limited to ``max_calls`` invocations.

    Create one instance per agent when agents should have independent budgets.
    """
    budget = _TwitterSearchBudget(max_calls=max_calls)
    description = (
        "Search X (Twitter) for the latest public discussion via the Grok CLI. "
        f"At most {max_calls} calls are available to this agent. Spend them on the "
        "highest-value social-signal queries only."
    )

    @tool("twitter_search", description=description)
    @_source_limited(_SOURCE_X, "twitter_search")
    def limited_twitter_search(
        query: Annotated[
            str,
            Field(
                min_length=1,
                description=(
                    "Topic or question to look up on X (Twitter) for the latest public "
                    "posts, discussion, sentiment, and breaking chatter"
                ),
            ),
        ],
    ) -> str:
        """Search X (Twitter) for the latest discussion via the Grok CLI."""
        ok, used, limit = budget.try_acquire()
        if not ok:
            return (
                f"twitter_search limit reached ({limit} calls for this agent). Do not call "
                "twitter_search again; rely on web_research and gathered evidence."
            )

        remaining = limit - used
        ai_log.info(
            "Searching X/Twitter for %s (%d/%d for this agent, %d remaining)",
            query,
            used,
            limit,
            remaining,
        )
        try:
            return _run_twitter_search(query)
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
            return _json(
                {
                    "ok": False,
                    "query": query,
                    "calls_used": used,
                    "calls_remaining": limit - used,
                    "error": str(exc),
                }
            )

    return limited_twitter_search


# Default tool instance for the primary agent. Use the factory for independent budgets.
twitter_search = build_twitter_search_tool()


@tool("web_research")
@_source_limited(_SOURCE_WEB, "web_research")
@redis_cached_tool("web_research", ttl_seconds=_CACHE_TTL_WEB_SECONDS)
async def web_research(query: str, max_results: int = 5) -> str:
    """Search the public web and summarize only the pages Midas successfully scraped.

    Use for recent news, events, or facts not available in Screener. The result
    includes a grounded summary plus source URLs and scrape statuses.

    Args:
        query: Precise web-search query.
        max_results: Number of pages to scrape, from 1 to 10 (default 5).
    """
    ai_log.info("Searching the web for %s (up to %d results)", query, max_results)
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
@_source_limited(_SOURCE_FUNDAMENTALS, "company_fundamentals")
@redis_cached_tool("company_fundamentals", ttl_seconds=_CACHE_TTL_COMPANY_SECONDS)
async def company_fundamentals(symbol: str, consolidated: bool = False) -> str:
    """Fetch normal fundamentals provider company fundamentals and market data for an NSE symbol.

    Use for financial statements, ratios, peers, shareholding, company profile, and
    announcements. This intentionally does not download earnings-call transcripts;
    use ``earnings_transcripts`` when the user needs management commentary.

    Args:
        symbol: NSE/Screener trading symbol, for example RELIANCE, TCS, or INFY.
        consolidated: Whether to request consolidated rather than standalone figures.
    """
    ai_log.info("Fetching Screener fundamentals for %s", symbol)
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
    return _json(
        {
            "ok": True,
            "symbol": result.symbol,
            "source_urls": list(result.source_urls),
            # Keep the structured snapshot and omit the duplicate Markdown rendering.
            "data": {
                key: value
                for key, value in payload.items()
                if key != "agent_brief_markdown"
            },
        }
    )


@tool("earnings_transcripts")
@_source_limited(_SOURCE_FUNDAMENTALS, "earnings_transcripts")
@redis_cached_tool("earnings_transcripts", ttl_seconds=_CACHE_TTL_TRANSCRIPT_SECONDS)
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

    ai_log.info("Fetching the latest %d Screener concalls for %s", limit, symbol)
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
            "transcripts": [
                {
                    "date_label": transcript.date_label,
                    "transcript_url": transcript.transcript_url,
                    "status": transcript.status,
                    "page_count": transcript.page_count,
                    "char_count": transcript.char_count,
                    "summary": transcript.summary,
                    "excerpt": transcript.excerpt if not transcript.summary else None,
                    "error": transcript.error,
                }
                for transcript in transcripts
            ],
            "available_concall_links": [
                {"date_label": call.date_label, "transcript_url": call.transcript_url}
                for call in result.page.concalls
                if call.transcript_url
            ],
        }
    )


@tool("market_signals")
@_source_limited(_SOURCE_SIGNALS, "market_signals")
@redis_cached_tool("market_signals", ttl_seconds=_CACHE_TTL_COMPANY_SECONDS)
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
    ai_log.info("Fetching signals provider signals for %s", symbol)
    try:
        result = await scrape_signals(symbol)
    except (signals providerError, ValueError) as exc:
        return _json({"ok": False, "symbol": symbol, "error": str(exc)})

    return _json(
        {
            "ok": True,
            "symbol": result.symbol,
            "source_urls": list(result.source_urls),
            # The payload contains the same facts as the Markdown brief without duplication.
            "data": result.agent_payload(),
        }
    )


@tool("nse_list_index")
@_source_limited(_SOURCE_NSE, "nse_list_index")
@redis_cached_tool("nse_list_index", ttl_seconds=_CACHE_TTL_LIVE_SECONDS)
def nse_list_index(
    index: Annotated[
        NseIndex,
        Field(
            description=(
                "NSE index or special list whose constituents to return. "
                "Use NIFTY_50 for the Nifty 50 companies, NIFTY_BANK for banks, "
                "SECURITIES_IN_F_AND_O for F&O underlyings, etc."
            ),
        ),
    ] = NseIndex.NIFTY_50,
) -> str:
    """List live NSE equity constituents for a named index or special list.

    Use when the user asks which stocks are in Nifty 50, Bank Nifty, sectoral
    indices, F&O universe, or similar. Returns compact rows (symbol, optional
    company name, last price, day change) from the unofficial NseIndiaApi client.
    Not an official NSE data product.

    Args:
        index: Allowed NSE index name from the NseIndex enum (default NIFTY_50).
    """
    ai_log.info("Listing NSE index constituents for %s", index.value)
    try:
        raw = _fetch_nse_index_list(index)
    except _MARKET_TOOL_ERRORS as exc:
        return _json(
            {
                "ok": False,
                "index": index.value,
                "error": str(exc),
            }
        )

    index_name = index.value
    elements: list[dict[str, Any]] = []
    for row in raw.get("data") or []:
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol")
        if not symbol:
            continue
        # NSE returns the index itself as the first row; keep only members.
        if str(symbol).upper() == index_name.upper():
            continue
        elements.append(_compact_index_row(row))

    market_status = raw.get("marketStatus") if isinstance(raw.get("marketStatus"), dict) else {}
    source_url = f"{_NSE_EQUITY_MARKET_URL}?symbol={index_name.replace(' ', '%20')}"

    payload = {
        "index": index_name,
        "count": len(elements),
        "timestamp": raw.get("timestamp"),
        "market_status": market_status.get("marketStatus"),
        "source_url": source_url,
        "elements": elements,
    }
    return _json({"ok": True, **payload})


@tool("nse_company_filings")
@_source_limited(_SOURCE_NSE, "nse_company_filings")
@redis_cached_tool("nse_company_filings", ttl_seconds=_CACHE_TTL_MARKET_SECONDS)
def nse_company_filings(
    symbol: str,
    lookback_days: int = 90,
    limit_per_section: int = 10,
) -> str:
    """Fetch official NSE filing feeds for one company through an unofficial client.

    Use for recent announcements, corporate actions, board meetings, result
    filings, quarterly result comparisons, shareholding, and annual-report links.
    A failure in one feed is reported as a warning without discarding other feeds.

    Args:
        symbol: NSE equity symbol, for example RELIANCE, TCS, or INFY.
        lookback_days: Filing lookback from 1 to 365 days (default 90).
        limit_per_section: Maximum rows returned per section, from 1 to 25.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        return _json({"ok": False, "error": "symbol must not be empty"})
    if not 1 <= lookback_days <= 365:
        return _json({"ok": False, "symbol": symbol, "error": "lookback_days must be 1..365"})
    if not 1 <= limit_per_section <= 25:
        return _json(
            {"ok": False, "symbol": symbol, "error": "limit_per_section must be 1..25"}
        )
    ai_log.info("Fetching NSE company filings for %s", symbol)
    try:
        result = fetch_nse_company_filings(
            symbol,
            lookback_days=lookback_days,
            limit_per_section=limit_per_section,
        )
    except _MARKET_TOOL_ERRORS as exc:
        return _json({"ok": False, "symbol": symbol, "error": str(exc)})
    return _json({"ok": True, **result})


@tool("nse_equity_snapshot")
@_source_limited(_SOURCE_NSE, "nse_equity_snapshot")
@redis_cached_tool("nse_equity_snapshot", ttl_seconds=_CACHE_TTL_LIVE_SECONDS)
def nse_equity_snapshot(symbol: str) -> str:
    """Fetch a live NSE equity quote and security identity snapshot.

    Use for current price, OHLC, volume, delivery, price bands, 52-week context,
    security status, ISIN, and F&O/ETF classification. Use Screener instead for
    financial statements, ratios, and peers.

    Args:
        symbol: NSE equity symbol, for example RELIANCE, TCS, or INFY.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        return _json({"ok": False, "error": "symbol must not be empty"})
    ai_log.info("Fetching NSE equity snapshot for %s", symbol)
    try:
        result = fetch_nse_equity_snapshot(symbol)
    except _MARKET_TOOL_ERRORS as exc:
        return _json({"ok": False, "symbol": symbol, "error": str(exc)})
    return _json({"ok": True, **result})


@tool("equity_trading_history")
@_source_limited(_SOURCE_NSE, "equity_trading_history")
@redis_cached_tool("equity_trading_history", ttl_seconds=_CACHE_TTL_MARKET_SECONDS)
def equity_trading_history(symbol: str, lookback_days: int = 90) -> str:
    """Summarize NSE price, volume, volatility, drawdown, and delivery history.

    Returns compact performance statistics plus at most ten recent observations,
    not an unbounded daily series.

    Args:
        symbol: NSE equity symbol, for example RELIANCE, TCS, or INFY.
        lookback_days: Calendar-day lookback from 7 to 1825 days.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        return _json({"ok": False, "error": "symbol must not be empty"})
    if not 7 <= lookback_days <= 1825:
        return _json({"ok": False, "symbol": symbol, "error": "lookback_days must be 7..1825"})
    ai_log.info("Fetching %d-day NSE trading history for %s", lookback_days, symbol)
    try:
        result = fetch_equity_trading_history(symbol, lookback_days=lookback_days)
    except _MARKET_TOOL_ERRORS as exc:
        return _json({"ok": False, "symbol": symbol, "error": str(exc)})
    return _json({"ok": True, **result})


@tool("nse_market_scan")
@_source_limited(_SOURCE_NSE, "nse_market_scan")
@redis_cached_tool("nse_market_scan", ttl_seconds=_CACHE_TTL_LIVE_SECONDS)
def nse_market_scan(
    index: NseIndex = NseIndex.NIFTY_500,
    limit: int = 10,
) -> str:
    """Scan an NSE universe for breadth, movers, activity, and India VIX context.

    Args:
        index: NSE index or equity universe to scan (default NIFTY 500).
        limit: Maximum gainers, losers, volume gainers, and active rows, from 1 to 25.
    """
    if not 1 <= limit <= 25:
        return _json({"ok": False, "index": index.value, "error": "limit must be 1..25"})
    ai_log.info("Scanning %s market breadth and movers", index.value)
    try:
        result = fetch_nse_market_scan(index.value, limit=limit)
    except _MARKET_TOOL_ERRORS as exc:
        return _json({"ok": False, "index": index.value, "error": str(exc)})
    return _json({"ok": True, **result})


@tool("equity_event_calendar")
@_source_limited(_SOURCE_NSE, "equity_event_calendar")
@redis_cached_tool("equity_event_calendar", ttl_seconds=_CACHE_TTL_MARKET_SECONDS)
def equity_event_calendar(
    symbol: str | None = None,
    lookback_days: int = 7,
    forward_days: int = 30,
    limit_per_section: int = 25,
) -> str:
    """Find recent and upcoming NSE equity results and corporate events.

    Use without a symbol for catalyst discovery across the market, or provide one
    to filter results, board events, dividends, splits, bonuses, and other actions.

    Args:
        symbol: Optional NSE equity symbol.
        lookback_days: Days before today to include, from 0 to 90.
        forward_days: Days after today to include, from 1 to 365.
        limit_per_section: Maximum rows returned per section, from 1 to 50.
    """
    normalized_symbol = symbol.strip().upper() if symbol else None
    if symbol is not None and not normalized_symbol:
        return _json({"ok": False, "error": "symbol must not be blank"})
    if not 0 <= lookback_days <= 90:
        return _json({"ok": False, "error": "lookback_days must be 0..90"})
    if not 1 <= forward_days <= 365:
        return _json({"ok": False, "error": "forward_days must be 1..365"})
    if not 1 <= limit_per_section <= 50:
        return _json({"ok": False, "error": "limit_per_section must be 1..50"})
    ai_log.info("Fetching NSE event calendar for %s", normalized_symbol or "the market")
    try:
        result = fetch_equity_event_calendar(
            normalized_symbol,
            lookback_days=lookback_days,
            forward_days=forward_days,
            limit=limit_per_section,
        )
    except _MARKET_TOOL_ERRORS as exc:
        return _json({"ok": False, "symbol": normalized_symbol, "error": str(exc)})
    return _json({"ok": True, **result})


@tool("exchange_deals")
@_source_limited(_SOURCE_NSE, "exchange_deals")
@redis_cached_tool("exchange_deals", ttl_seconds=_CACHE_TTL_MARKET_SECONDS)
def exchange_deals(
    symbol: str | None = None,
    lookback_days: int = 30,
    deal_types: list[DealType] | None = None,
    limit_per_type: int = 25,
) -> str:
    """Fetch NSE bulk deals, block deals, and reported short-selling activity.

    Args:
        symbol: Optional NSE equity symbol; omit for market-wide activity.
        lookback_days: Calendar-day lookback from 1 to 365.
        deal_types: Categories to fetch; defaults to bulk, block, and short.
        limit_per_type: Maximum rows returned for each category, from 1 to 50.
    """
    normalized_symbol = symbol.strip().upper() if symbol else None
    if symbol is not None and not normalized_symbol:
        return _json({"ok": False, "error": "symbol must not be blank"})
    if not 1 <= lookback_days <= 365:
        return _json({"ok": False, "error": "lookback_days must be 1..365"})
    if not 1 <= limit_per_type <= 50:
        return _json({"ok": False, "error": "limit_per_type must be 1..50"})
    selected = deal_types or [DealType.BULK, DealType.BLOCK, DealType.SHORT]
    names = list(dict.fromkeys(item.value for item in selected))
    if not names:
        return _json({"ok": False, "error": "deal_types must not be empty"})
    ai_log.info("Fetching exchange deals for %s", normalized_symbol or "the market")
    try:
        result = fetch_exchange_deals(
            normalized_symbol,
            lookback_days=lookback_days,
            deal_types=names,
            limit=limit_per_type,
        )
    except _MARKET_TOOL_ERRORS as exc:
        return _json({"ok": False, "symbol": normalized_symbol, "error": str(exc)})
    return _json({"ok": True, **result})


@tool("nse_derivatives_snapshot")
@_source_limited(_SOURCE_NSE, "nse_derivatives_snapshot")
@redis_cached_tool("nse_derivatives_snapshot", ttl_seconds=_CACHE_TTL_LIVE_SECONDS)
def nse_derivatives_snapshot(
    symbol: str,
    expiry: str | None = None,
    strikes_each_side: int = 5,
) -> str:
    """Summarize an NSE option chain around ATM with positioning and risk context.

    Returns PCR, max pain, maximum call/put OI, OI changes, lot size, F&O-ban
    status, and a bounded strike window. The nearest expiry is used by default.

    Args:
        symbol: NSE F&O equity or index, for example TCS, NIFTY, or BANKNIFTY.
        expiry: Optional ISO expiry date (YYYY-MM-DD); omit for nearest expiry.
        strikes_each_side: Number of strikes on each side of ATM, from 1 to 10.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        return _json({"ok": False, "error": "symbol must not be empty"})
    parsed_expiry: date | None = None
    if expiry:
        try:
            parsed_expiry = date.fromisoformat(expiry)
        except ValueError:
            return _json({"ok": False, "symbol": symbol, "error": "expiry must use YYYY-MM-DD"})
        if parsed_expiry < date.today():
            return _json({"ok": False, "symbol": symbol, "error": "expiry cannot be in the past"})
    if not 1 <= strikes_each_side <= 10:
        return _json({"ok": False, "symbol": symbol, "error": "strikes_each_side must be 1..10"})
    ai_log.info("Fetching NSE derivatives snapshot for %s", symbol)
    try:
        result = fetch_nse_derivatives_snapshot(
            symbol,
            expiry=parsed_expiry,
            strikes_each_side=strikes_each_side,
        )
    except _MARKET_TOOL_ERRORS as exc:
        return _json({"ok": False, "symbol": symbol, "error": str(exc)})
    return _json({"ok": True, **result})


@tool("institutional_activity")
@_source_limited(_SOURCE_NSE, "institutional_activity")
@redis_cached_tool("institutional_activity", ttl_seconds=_CACHE_TTL_MARKET_SECONDS)
def institutional_activity(trade_date: str | None = None) -> str:
    """Fetch latest or historical Indian institutional cash and derivatives reports.

    With no date, returns the latest NSE FII/DII cash data and latest NSDL FPI
    investment/derivatives reports. With a date, returns date-specific NSDL,
    participant OI/volume, and FII derivatives reports.

    Args:
        trade_date: Optional ISO date (YYYY-MM-DD). Omit for latest reports.
    """
    parsed_date: date | None = None
    if trade_date:
        try:
            parsed_date = date.fromisoformat(trade_date)
        except ValueError:
            return _json({"ok": False, "error": "trade_date must use YYYY-MM-DD"})
        if parsed_date > date.today():
            return _json({"ok": False, "error": "trade_date cannot be in the future"})
    ai_log.info("Fetching %s institutional activity", parsed_date or "latest")
    try:
        result = fetch_institutional_activity(parsed_date)
    except (OSError, TimeoutError, ConnectionError, ImportError, ValueError, RuntimeError) as exc:
        return _json({"ok": False, "trade_date": trade_date, "error": str(exc)})
    return _json({"ok": True, **result})


@tool("india_market_context")
@_source_limited(_SOURCE_NSE, "india_market_context")
@redis_cached_tool("india_market_context", ttl_seconds=_CACHE_TTL_MARKET_SECONDS)
def india_market_context(
    index: MarketContextIndex = MarketContextIndex.NIFTY_50,
    commodities: list[McxCommodity] | None = None,
    lookback_days: int = 90,
) -> str:
    """Summarize a Nifty benchmark, its TRI, and relevant MCX commodity moves.

    Use for market-regime and cross-asset context around an Indian equity. Returns
    compact performance statistics rather than raw daily series.

    Args:
        index: Nifty benchmark to summarize (default NIFTY 50).
        commodities: Up to five MCX commodities (default CRUDEOIL and GOLD).
        lookback_days: Calendar-day lookback from 7 to 1825 days.
    """
    selected = commodities or [McxCommodity.CRUDEOIL, McxCommodity.GOLD]
    if not 7 <= lookback_days <= 1825:
        return _json({"ok": False, "error": "lookback_days must be 7..1825"})
    if not 1 <= len(selected) <= 5:
        return _json({"ok": False, "error": "commodities must contain 1..5 values"})
    names = list(dict.fromkeys(item.value for item in selected))
    ai_log.info("Fetching India market context for %s", index.value)
    try:
        result = fetch_india_market_context(
            index.value,
            names,
            lookback_days=lookback_days,
        )
    except (OSError, TimeoutError, ConnectionError, ImportError, ValueError, RuntimeError) as exc:
        return _json({"ok": False, "index": index.value, "error": str(exc)})
    return _json({"ok": True, **result})


# Scrape / market-data tools only (no web search, X, charts, or agent UI helpers).
# Exposed both to DeepAgents and to the standalone MCP server for external hosts.
#
# Each tool already has a per-upstream-source single-flight gate (screener /
# trendlyne / nse). The MCP server additionally serializes the whole set so
# external hosts that fire tools in parallel get the same sequential policy
# the in-app agents are instructed to follow.
MARKET_INFO_TOOLS = (
    company_fundamentals,
    earnings_transcripts,
    market_signals,
    nse_list_index,
    nse_company_filings,
    nse_equity_snapshot,
    equity_trading_history,
    nse_market_scan,
    equity_event_calendar,
    exchange_deals,
    nse_derivatives_snapshot,
    institutional_activity,
    india_market_context,
)

# Process-wide sequential slot used by the MCP adapter for all market-info tools.
MARKET_SEQUENTIAL_SOURCE = "market"

MIDAS_TOOLS = (
    send_update,
    web_research,
    *MARKET_INFO_TOOLS,
    twitter_search,
    *CHART_TOOLS,
)

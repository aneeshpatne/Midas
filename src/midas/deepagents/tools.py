"""Agent-safe wrappers around Midas research capabilities.

Each tool returns compact JSON so a DeepAgent can cite the source URL and decide
which follow-up lookup to make without receiving the full raw scraper payload.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import threading
from enum import StrEnum
from typing import Annotated, Any

from langchain_core.tools import BaseTool, tool
from langgraph.config import get_stream_writer
from pydantic import Field

from ..pipeline import MidasError, search_and_scrape
from ..fundamentals import FundamentalsError, scrape_company
from ..signals import signals providerError, scrape_signals

TWITTER_SEARCH_MAX_CALLS = 2
"""Default maximum number of Grok/X searches available to one agent."""

_TWITTER_SEARCH_TIMEOUT_S = 60

_NSE_EQUITY_MARKET_URL = "https://www.nseindia.com/market-data/live-equity-market"

ai_log = logging.getLogger(__name__)


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


def _json(data: dict[str, Any]) -> str:
    """Serialize tool output consistently for model consumption."""
    return json.dumps(data, ensure_ascii=False, default=str)


def _compact_index_row(row: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields useful for listing index members."""
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    return {
        "symbol": row.get("symbol"),
        "identifier": row.get("identifier"),
        "company_name": meta.get("companyName") or meta.get("company_name"),
        "series": row.get("series"),
        "last_price": row.get("lastPrice"),
        "p_change": row.get("pChange"),
        "open": row.get("open"),
        "day_high": row.get("dayHigh"),
        "day_low": row.get("dayLow"),
        "previous_close": row.get("previousClose"),
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
            "brief": result.agent_brief(),
            "data": result.agent_payload(),
        }
    )


@tool("nse_list_index")
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
    except (OSError, TimeoutError, ConnectionError, ImportError, ValueError, RuntimeError) as exc:
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

    return _json(
        {
            "ok": True,
            "index": index_name,
            "count": len(elements),
            "timestamp": raw.get("timestamp"),
            "market_status": market_status.get("marketStatus"),
            "source_url": source_url,
            "elements": elements,
        }
    )


MIDAS_TOOLS = (
    send_update,
    web_research,
    company_fundamentals,
    earnings_transcripts,
    market_signals,
    nse_list_index,
    twitter_search,
)

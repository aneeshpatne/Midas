import asyncio
import json
import logging

import pytest

from midas.deepagents import tools
from midas.models import ScrapeStatus, SearchResult, SourceResult
from midas.fundamentals.models import CompanyPage, CompanyProfile, ReportingBasis, CompanyFundamentalsResult
from midas.signals.models import StockIdentity, signals providerSignalsResult


@pytest.mark.asyncio
async def test_web_research_wraps_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search(query: str, *, max_results: int) -> SearchResult:
        assert (query, max_results) == ("tata motors news", 2)
        return SearchResult(
            query=query,
            compressed="Grounded result",
            sources=(
                SourceResult(
                    source_id="S1",
                    title="Example",
                    url="https://example.com/article",
                    status=ScrapeStatus.SUCCESS,
                    content="source text",
                ),
            ),
        )

    monkeypatch.setattr(tools, "search_and_scrape", fake_search)
    response = json.loads(
        await tools.web_research.ainvoke({"query": "tata motors news", "max_results": 2})
    )
    assert response["ok"] is True
    assert response["summary"] == "Grounded result"
    assert response["sources"][0]["url"] == "https://example.com/article"


@pytest.mark.asyncio
async def test_screener_tools_use_distinct_concall_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    page = CompanyPage(
        url="https://www.fundamentals provider/company/TCS/",
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

    async def fake_scrape(symbol: str, **kwargs: object) -> CompanyFundamentalsResult:
        calls.append({"symbol": symbol, **kwargs})
        return result

    monkeypatch.setattr(tools, "scrape_company", fake_scrape)
    await tools.company_fundamentals.ainvoke({"symbol": "TCS"})
    await tools.earnings_transcripts.ainvoke({"symbol": "TCS", "limit": 3, "summarize": False})

    assert calls[0]["include_concalls"] is False
    assert calls[0]["include_chart"] is True
    assert calls[1]["include_concalls"] is True
    assert calls[1]["concall_limit"] == 3
    assert calls[1]["summarize_concalls"] is False


@pytest.mark.asyncio
async def test_same_source_call_returns_busy_immediately_and_slot_is_released(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[dict[str, object]] = []
    page = CompanyPage(
        url="https://www.fundamentals provider/company/TCS/",
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

    async def fake_scrape(symbol: str, **kwargs: object) -> CompanyFundamentalsResult:
        calls.append({"symbol": symbol, **kwargs})
        started.set()
        await release.wait()
        return result

    monkeypatch.setattr(tools, "scrape_company", fake_scrape)

    first = asyncio.create_task(tools.company_fundamentals.ainvoke({"symbol": "TCS"}))
    await asyncio.wait_for(started.wait(), timeout=1)

    busy = json.loads(
        await asyncio.wait_for(
            tools.earnings_transcripts.ainvoke({"symbol": "TCS"}), timeout=0.1
        )
    )
    assert busy == {
        "ok": False,
        "status": "busy",
        "retryable": True,
        "source": "screener",
        "tool": "earnings_transcripts",
        "message": (
            "Another screener tool is already running. Wait for it to finish, then retry "
            "earnings_transcripts; do not start another screener tool while it is busy."
        ),
    }
    assert len(calls) == 1

    release.set()
    assert json.loads(await first)["ok"] is True

    released = json.loads(await tools.earnings_transcripts.ainvoke({"symbol": "TCS"}))
    assert released["ok"] is True
    assert len(calls) == 2


def test_source_gate_is_nonblocking_and_allows_different_sources() -> None:
    gate = tools._SourceConcurrencyGate()

    assert gate.try_acquire("screener") is True
    assert gate.try_acquire("screener") is False
    assert gate.try_acquire("trendlyne") is True
    gate.release("screener")
    gate.release("trendlyne")
    assert gate.try_acquire("screener") is True
    gate.release("screener")


@pytest.mark.asyncio
async def test_market_signals_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    identity = StockIdentity(
        stock_id=1372,
        symbol="TCS",
        name="Tata Consultancy Services Ltd",
        page_url="https://signals provider/equity/1372/TCS/tata-consultancy-services-ltd/",
    )
    result = signals providerSignalsResult(
        symbol="TCS",
        identity=identity,
        scraped_at="2026-07-28T00:00:00+00:00",
        source_urls=(identity.page_url,),
    )

    async def fake_signals(symbol: str, **kwargs: object) -> signals providerSignalsResult:
        assert symbol == "TCS"
        return result

    monkeypatch.setattr(tools, "scrape_signals", fake_signals)
    response = json.loads(await tools.market_signals.ainvoke({"symbol": "TCS"}))
    assert response["ok"] is True
    assert response["symbol"] == "TCS"
    assert "brief" in response
    assert response["data"]["name"] == "Tata Consultancy Services Ltd"


def test_send_update_emits_a_custom_stream_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    updates: list[dict[str, str]] = []

    monkeypatch.setattr(tools, "get_stream_writer", lambda: updates.append)

    response = tools.send_update.invoke({"update": "I found a primary source and am checking it."})

    assert response == "Progress update displayed successfully."
    assert updates == [
        {
            "type": "deep_agent_update",
            "update": "I found a primary source and am checking it.",
        }
    ]


def test_nse_list_index_returns_compact_constituents(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(index: tools.NseIndex) -> dict:
        assert index is tools.NseIndex.NIFTY_50
        return {
            "timestamp": "27-May-2026 11:54:31",
            "marketStatus": {"marketStatus": "Open"},
            "data": [
                {
                    "symbol": "NIFTY 50",
                    "identifier": "NIFTY 50",
                    "lastPrice": 23944.8,
                    "pChange": 0.13,
                    "series": None,
                },
                {
                    "symbol": "RELIANCE",
                    "identifier": "RELIANCE",
                    "series": "EQ",
                    "lastPrice": 1400.5,
                    "pChange": 1.2,
                    "open": 1380.0,
                    "dayHigh": 1410.0,
                    "dayLow": 1375.0,
                    "previousClose": 1383.0,
                    "totalTradedVolume": 1_000_000,
                    "meta": {"companyName": "Reliance Industries Limited"},
                },
                {
                    "symbol": "TCS",
                    "identifier": "TCS",
                    "series": "EQ",
                    "lastPrice": 3500.0,
                    "pChange": -0.5,
                    "meta": {"companyName": "Tata Consultancy Services Ltd"},
                },
            ],
        }

    monkeypatch.setattr(tools, "_fetch_nse_index_list", fake_fetch)
    response = json.loads(tools.nse_list_index.invoke({"index": "NIFTY 50"}))

    assert response["ok"] is True
    assert response["index"] == "NIFTY 50"
    assert response["count"] == 2
    assert response["market_status"] == "Open"
    assert "live-equity-market" in response["source_url"]
    assert [row["symbol"] for row in response["elements"]] == ["RELIANCE", "TCS"]
    assert response["elements"][0]["company_name"] == "Reliance Industries Limited"
    assert response["elements"][0]["last_price"] == 1400.5


def test_nse_list_index_reports_fetch_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_index: tools.NseIndex) -> dict:
        raise ConnectionError("NSE blocked the request")

    monkeypatch.setattr(tools, "_fetch_nse_index_list", boom)
    response = json.loads(tools.nse_list_index.invoke({"index": "NIFTY BANK"}))

    assert response["ok"] is False
    assert response["index"] == "NIFTY BANK"
    assert "blocked" in response["error"]


def test_nse_list_index_schema_exposes_index_enum() -> None:
    schema = tools.nse_list_index.tool_call_schema.model_json_schema()
    index_schema = schema["properties"]["index"]
    # Pydantic may inline enum values or $ref them; either form is fine for the agent.
    enum_values = index_schema.get("enum")
    if enum_values is None:
        defs = schema.get("$defs") or schema.get("definitions") or {}
        for definition in defs.values():
            if "enum" in definition and "NIFTY 50" in definition["enum"]:
                enum_values = definition["enum"]
                break
    assert enum_values is not None
    assert "NIFTY 50" in enum_values
    assert "SECURITIES IN F&O" in enum_values
    assert tools.NseIndex.NIFTY_50.value == "NIFTY 50"


def test_nse_company_filings_normalizes_symbol_and_validates_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int, int]] = []

    def fake_fetch(symbol: str, *, lookback_days: int, limit_per_section: int) -> dict:
        calls.append((symbol, lookback_days, limit_per_section))
        return {
            "symbol": symbol,
            "data": {"announcements": []},
            "warnings": [],
            "source_url": "https://www.nseindia.com/filings",
        }

    monkeypatch.setattr(tools, "fetch_nse_company_filings", fake_fetch)
    response = json.loads(
        tools.nse_company_filings.invoke(
            {"symbol": " tcs ", "lookback_days": 30, "limit_per_section": 5}
        )
    )

    assert response["ok"] is True
    assert response["symbol"] == "TCS"
    assert calls == [("TCS", 30, 5)]
    invalid = json.loads(
        tools.nse_company_filings.invoke(
            {"symbol": "TCS", "lookback_days": 0, "limit_per_section": 5}
        )
    )
    assert invalid["ok"] is False


def test_institutional_activity_parses_iso_date(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []

    def fake_fetch(trade_date):
        seen.append(trade_date)
        return {"mode": "historical", "data": {}, "warnings": []}

    monkeypatch.setattr(tools, "fetch_institutional_activity", fake_fetch)
    response = json.loads(tools.institutional_activity.invoke({"trade_date": "2026-07-28"}))

    assert response["ok"] is True
    assert seen[0].isoformat() == "2026-07-28"
    invalid = json.loads(tools.institutional_activity.invoke({"trade_date": "28-07-2026"}))
    assert invalid == {"ok": False, "error": "trade_date must use YYYY-MM-DD"}


def test_india_market_context_uses_enum_values_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_fetch(index: str, commodities: list[str], *, lookback_days: int) -> dict:
        calls.append((index, commodities, lookback_days))
        return {"data": {}, "warnings": []}

    monkeypatch.setattr(tools, "fetch_india_market_context", fake_fetch)
    response = json.loads(
        tools.india_market_context.invoke(
            {
                "index": "NIFTY METAL",
                "commodities": ["COPPER", "COPPER", "ZINC"],
                "lookback_days": 60,
            }
        )
    )

    assert response["ok"] is True
    assert calls == [("NIFTY METAL", ["COPPER", "ZINC"], 60)]


def test_market_tool_schemas_expose_enums() -> None:
    schema = tools.india_market_context.tool_call_schema.model_json_schema()
    rendered = json.dumps(schema)
    assert "NIFTY 50" in rendered
    assert "CRUDEOIL" in rendered
    assert tools.nse_company_filings in tools.MIDAS_TOOLS
    assert tools.institutional_activity in tools.MIDAS_TOOLS
    assert tools.india_market_context in tools.MIDAS_TOOLS


def test_new_equity_tools_validate_normalize_and_register(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        tools,
        "fetch_nse_equity_snapshot",
        lambda symbol: calls.append(("snapshot", symbol)) or {"symbol": symbol},
    )
    monkeypatch.setattr(
        tools,
        "fetch_equity_trading_history",
        lambda symbol, **kwargs: calls.append(("history", (symbol, kwargs))) or {"symbol": symbol},
    )
    monkeypatch.setattr(
        tools,
        "fetch_nse_market_scan",
        lambda index, **kwargs: calls.append(("scan", (index, kwargs))) or {"index_name": index},
    )
    monkeypatch.setattr(
        tools,
        "fetch_equity_event_calendar",
        lambda symbol, **kwargs: calls.append(("events", (symbol, kwargs)))
        or {"symbol": symbol},
    )
    monkeypatch.setattr(
        tools,
        "fetch_exchange_deals",
        lambda symbol, **kwargs: calls.append(("deals", (symbol, kwargs)))
        or {"symbol": symbol},
    )
    monkeypatch.setattr(
        tools,
        "fetch_nse_derivatives_snapshot",
        lambda symbol, **kwargs: calls.append(("derivatives", (symbol, kwargs)))
        or {"symbol": symbol},
    )

    assert json.loads(tools.nse_equity_snapshot.invoke({"symbol": " tcs "}))["ok"] is True
    assert json.loads(
        tools.equity_trading_history.invoke({"symbol": " tcs ", "lookback_days": 30})
    )["ok"] is True
    assert json.loads(tools.nse_market_scan.invoke({"index": "NIFTY 50", "limit": 5}))[
        "ok"
    ] is True
    assert json.loads(tools.equity_event_calendar.invoke({"symbol": " tcs "}))["ok"] is True
    assert json.loads(
        tools.exchange_deals.invoke(
            {"symbol": " tcs ", "deal_types": ["bulk", "bulk", "short"]}
        )
    )["ok"] is True
    assert json.loads(
        tools.nse_derivatives_snapshot.invoke(
            {"symbol": " tcs ", "expiry": "2026-08-27", "strikes_each_side": 3}
        )
    )["ok"] is True

    assert calls[0] == ("snapshot", "TCS")
    assert calls[1][0] == "history"
    assert calls[2] == ("scan", ("NIFTY 50", {"limit": 5}))
    assert calls[4][1][1]["deal_types"] == ["bulk", "short"]
    assert calls[5][1][1]["expiry"].isoformat() == "2026-08-27"

    new_tools = [
        tools.nse_equity_snapshot,
        tools.equity_trading_history,
        tools.nse_market_scan,
        tools.equity_event_calendar,
        tools.exchange_deals,
        tools.nse_derivatives_snapshot,
    ]
    assert all(item in tools.MIDAS_TOOLS for item in new_tools)
    assert "bulk" in json.dumps(tools.exchange_deals.tool_call_schema.model_json_schema())
    assert "NIFTY 500" in json.dumps(tools.nse_market_scan.tool_call_schema.model_json_schema())


def test_new_equity_tool_bounds_fail_before_provider_calls() -> None:
    assert json.loads(
        tools.equity_trading_history.invoke({"symbol": "TCS", "lookback_days": 2})
    )["ok"] is False
    assert json.loads(tools.nse_market_scan.invoke({"limit": 0}))["ok"] is False
    assert json.loads(tools.equity_event_calendar.invoke({"forward_days": 0}))["ok"] is False
    assert json.loads(tools.exchange_deals.invoke({"lookback_days": 0}))["ok"] is False
    assert json.loads(
        tools.nse_derivatives_snapshot.invoke({"symbol": "TCS", "strikes_each_side": 20})
    )["ok"] is False


def test_twitter_search_tool_limits_calls_and_reports_failures(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[str] = []

    def fake_search(query: str) -> str:
        calls.append(query)
        return "Latest X discussion"

    monkeypatch.setattr(tools, "_run_twitter_search", fake_search)
    twitter_search = tools.build_twitter_search_tool(max_calls=1)
    caplog.set_level(logging.INFO, logger="midas.deepagents.tools")

    assert twitter_search.invoke({"query": "TCS results"}) == "Latest X discussion"
    assert "limit reached" in twitter_search.invoke({"query": "TCS guidance"})
    assert calls == ["TCS results"]
    assert "Searching X/Twitter for TCS results (1/1 for this agent, 0 remaining)" in caplog.text

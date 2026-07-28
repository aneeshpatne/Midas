import json

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

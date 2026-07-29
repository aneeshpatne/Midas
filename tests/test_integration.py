import os

import pytest

from midas import ScrapeStatus, pipeline


@pytest.mark.integration
@pytest.mark.asyncio
async def test_camoufox_scrapes_and_cleans_a_public_html_page() -> None:
    if os.getenv("MIDAS_RUN_INTEGRATION") != "1":
        pytest.skip("Set MIDAS_RUN_INTEGRATION=1 to run the browser smoke test")

    hits = (
        pipeline._SearchHit(
            source_id="S1",
            title="Example Domain",
            url="https://example.com/",
        ),
    )

    sources = await pipeline._scrape_hits(hits)

    assert sources[0].status is ScrapeStatus.SUCCESS
    assert sources[0].content


@pytest.mark.integration
@pytest.mark.asyncio
async def test_http_fallback_scrapes_when_camoufox_cannot_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.getenv("MIDAS_RUN_INTEGRATION") != "1":
        pytest.skip("Set MIDAS_RUN_INTEGRATION=1 to run the browser smoke test")

    class BrokenCamoufox:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> object:
            raise ValueError("bad value(s) in fds_to_keep")

        async def __aexit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(pipeline, "AsyncCamoufox", BrokenCamoufox)
    hits = (
        pipeline._SearchHit(
            source_id="S1",
            title="Example Domain",
            url="https://example.com/",
        ),
    )

    sources = await pipeline._scrape_hits(hits)

    assert sources[0].status is ScrapeStatus.SUCCESS
    assert sources[0].content

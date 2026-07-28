import pytest
from pydantic import ValidationError

from midas import ScrapeStatus, SearchResult, SourceResult


def test_successful_source_requires_content() -> None:
    with pytest.raises(ValidationError):
        SourceResult(
            source_id="S1",
            title="Example",
            url="https://example.com",
            status=ScrapeStatus.SUCCESS,
        )


def test_failed_source_requires_error() -> None:
    with pytest.raises(ValidationError):
        SourceResult(
            source_id="S1",
            title="Example",
            url="https://example.com",
            status=ScrapeStatus.FAILED,
        )


def test_search_result_text_is_compressed_output() -> None:
    result = SearchResult(
        query="batteries",
        compressed="Scraped pages say sodium-ion batteries use abundant materials [S1].",
        sources=(
            SourceResult(
                source_id="S1",
                title="Good page",
                url="https://example.com/good",
                status=ScrapeStatus.SUCCESS,
                content="Sodium-ion batteries use abundant materials.",
            ),
            SourceResult(
                source_id="S2",
                title="Broken",
                url="https://example.com/bad",
                status=ScrapeStatus.FAILED,
                error="Timed out",
            ),
        ),
    )

    assert result.text() == result.compressed
    assert "abundant materials" in result.compressed

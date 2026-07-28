import pytest
from pydantic import ValidationError

from midas import ScrapeStatus, SourceResult


def test_successful_source_requires_excerpt() -> None:
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

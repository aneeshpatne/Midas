"""Typed results returned by the Midas web search pipeline."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScrapeStatus(StrEnum):
    """Outcome of scraping one search result."""

    SUCCESS = "success"
    FAILED = "failed"


class SourceResult(BaseModel):
    """One search hit after scrape and local cleaning."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(pattern=r"^S[1-9][0-9]*$")
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    status: ScrapeStatus
    content: str | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_status_fields(self) -> "SourceResult":
        if self.status is ScrapeStatus.SUCCESS:
            if not self.content:
                raise ValueError("A successful source must include scraped content")
            if self.error is not None:
                raise ValueError("A successful source cannot include an error")
        elif not self.error:
            raise ValueError("A failed source must include an error")
        return self


class SearchResult(BaseModel):
    """Search query, AI compression of scraped text, and source records."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1)
    compressed: str = Field(min_length=1)
    sources: tuple[SourceResult, ...] = Field(min_length=1)

    def text(self) -> str:
        """Return the compressed statement of what was scraped."""
        return self.compressed

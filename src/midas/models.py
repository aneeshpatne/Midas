"""Typed results returned by the Midas pipeline."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScrapeStatus(StrEnum):
    """Outcome of scraping one search result."""

    SUCCESS = "success"
    FAILED = "failed"


class SourceResult(BaseModel):
    """Public metadata and status for one source."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(pattern=r"^S[1-9][0-9]*$")
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    status: ScrapeStatus
    excerpt: str | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_status_fields(self) -> "SourceResult":
        if self.status is ScrapeStatus.SUCCESS:
            if not self.excerpt:
                raise ValueError("A successful source must include an excerpt")
            if self.error is not None:
                raise ValueError("A successful source cannot include an error")
        elif not self.error:
            raise ValueError("A failed source must include an error")
        return self


class ResearchResult(BaseModel):
    """A neutral digest and the sources considered while producing it."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1)
    digest: str = Field(min_length=1)
    sources: tuple[SourceResult, ...] = Field(min_length=1)

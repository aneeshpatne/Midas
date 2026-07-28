"""Midas public API."""

from .models import ScrapeStatus, SearchResult, SourceResult
from .pipeline import (
    CompressionError,
    MidasError,
    ScrapeError,
    SearchError,
    search_and_scrape,
    web_search,
)

__all__ = [
    "CompressionError",
    "MidasError",
    "ScrapeError",
    "ScrapeStatus",
    "SearchError",
    "SearchResult",
    "SourceResult",
    "search_and_scrape",
    "web_search",
]

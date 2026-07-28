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
from .fundamentals import (
    CompanyNotFoundError,
    CompanyFundamentalsResult,
    FundamentalsError,
    FundamentalsScraper,
    scrape_company,
    scrape_company_sync,
    search_companies,
    search_companies_sync,
)

__all__ = [
    "CompressionError",
    "CompanyNotFoundError",
    "MidasError",
    "ScrapeError",
    "ScrapeStatus",
    "CompanyFundamentalsResult",
    "FundamentalsError",
    "FundamentalsScraper",
    "SearchError",
    "SearchResult",
    "SourceResult",
    "scrape_company",
    "scrape_company_sync",
    "search_and_scrape",
    "search_companies",
    "search_companies_sync",
    "web_search",
]

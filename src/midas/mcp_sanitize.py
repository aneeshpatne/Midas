"""Sanitize values crossing the MCP boundary.

External hosts must never receive vendor URLs, absolute links, or URL-bearing
fields from Midas MCP tools. Internal scrapers may still use those endpoints;
only the MCP wire format is scrubbed.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Keys whose values are dropped entirely (not redacted in place).
_URL_KEY_RE = re.compile(
    r"(^|_)(urls?|href|uri|link|page_url|source_url|source_urls|"
    r"transcript_url|recording_url|ppt_url|summary_url|website|"
    r"logo_url|image_url|attachment|attachement)s?$",
    re.IGNORECASE,
)

_HTTP_URL_RE = re.compile(r"https?://[^\s\"'<>\\]+", re.IGNORECASE)

# Vendor / exchange hosts that must not appear in MCP text even without a scheme.
_HOST_RE = re.compile(
    r"\b("
    r"tickertape\.in|api\.tickertape\.in|"
    r"trendlyne\.com|"
    r"screener\.in|"
    r"moneycontrol\.com|"
    r"nseindia\.com|"
    r"bseindia\.com|"
    r"niftyindices\.com|"
    r"mcxindia\.com|"
    r"fpi\.nsdl\.co\.in|"
    r"openrouter\.ai|"
    r"tradingview\.com"
    r")\b",
    re.IGNORECASE,
)

_VENDOR_NAME_RE = re.compile(
    r"\b(Tickertape|Trendlyne|Screener\.in|Moneycontrol|NseIndiaApi|"
    r"TradingView|OpenRouter)\b",
    re.IGNORECASE,
)

# Example tickers often used in tool docs — strip from MCP-facing descriptions.
_EXAMPLE_SYMBOL_RE = re.compile(
    r"(?:,?\s*)?(?:for example|e\.g\.|eg\.)[^.\n]*",
    re.IGNORECASE,
)


def is_urlish_key(key: str) -> bool:
    return bool(_URL_KEY_RE.search(str(key)))


def scrub_text(value: str) -> str:
    """Remove absolute URLs and known vendor hosts/names from free text."""
    text = _HTTP_URL_RE.sub("[redacted]", value)
    text = _HOST_RE.sub("[redacted]", text)
    text = _VENDOR_NAME_RE.sub("market data", text)
    return text


def sanitize_for_mcp(value: Any) -> Any:
    """Recursively drop URL fields and scrub URL-like strings for MCP output."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if is_urlish_key(str(key)):
                continue
            cleaned[str(key)] = sanitize_for_mcp(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize_for_mcp(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_for_mcp(item) for item in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value


def sanitize_mcp_json_text(text: str) -> str:
    """Sanitize a JSON string payload; fall back to text scrub if not JSON."""
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return scrub_text(str(text))
    return json.dumps(
        sanitize_for_mcp(payload),
        ensure_ascii=False,
        default=str,
    )


def sanitize_tool_description(description: str | None) -> str:
    """MCP-facing tool description: no vendors, example tickers, or URLs."""
    if not description:
        return "Market information tool."
    text = scrub_text(description)
    text = _EXAMPLE_SYMBOL_RE.sub("", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text or "Market information tool."

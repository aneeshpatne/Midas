"""MCP wire sanitization — no external URLs or vendor hosts leave the process."""

from __future__ import annotations

import json

from midas.mcp_sanitize import (
    sanitize_for_mcp,
    sanitize_mcp_json_text,
    sanitize_tool_description,
)


def test_drops_url_keys_and_nested_urls() -> None:
    payload = {
        "ok": True,
        "symbol": "DEMO",
        "source_url": "https://www.nseindia.com/get-quotes/equity?symbol=DEMO",
        "source_urls": ["https://www.tickertape.in/stocks/demo"],
        "data": {
            "website": "https://example.com",
            "peers": [{"name": "Peer", "url": "https://trendlyne.com/equity/1/X/"}],
            "note": "See https://screener.in/company/DEMO/ for more",
        },
    }
    cleaned = sanitize_for_mcp(payload)
    assert "source_url" not in cleaned
    assert "source_urls" not in cleaned
    assert "website" not in cleaned["data"]
    assert "url" not in cleaned["data"]["peers"][0]
    assert "https://" not in json.dumps(cleaned)
    assert "tickertape" not in json.dumps(cleaned).lower()
    assert "nseindia" not in json.dumps(cleaned).lower()
    assert "[redacted]" in cleaned["data"]["note"]


def test_sanitize_mcp_json_text_roundtrip() -> None:
    raw = json.dumps(
        {
            "ok": True,
            "transcript_url": "https://www.bseindia.com/file.pdf",
            "summary": "Host tickertape.in mentioned",
        }
    )
    out = json.loads(sanitize_mcp_json_text(raw))
    assert "transcript_url" not in out
    assert "tickertape.in" not in out["summary"].lower()
    assert "https://" not in json.dumps(out)


def test_tool_description_strips_vendors_and_examples() -> None:
    desc = (
        "Fetch company fundamentals (Tickertape). "
        "Args: symbol for example RELIANCE, TCS, or INFY. "
        "See https://www.tickertape.in/stocks/x"
    )
    cleaned = sanitize_tool_description(desc)
    assert "Tickertape" not in cleaned
    assert "RELIANCE" not in cleaned
    assert "https://" not in cleaned
    assert "tickertape" not in cleaned.lower()

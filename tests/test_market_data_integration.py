import json
import os

import pytest

from midas.deepagents import tools

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("MIDAS_RUN_INTEGRATION") != "1",
        reason="Set MIDAS_RUN_INTEGRATION=1 to run live market-data smoke tests",
    ),
]


def test_live_nse_company_filings() -> None:
    response = json.loads(
        tools.nse_company_filings.invoke(
            {"symbol": "TCS", "lookback_days": 30, "limit_per_section": 1}
        )
    )
    assert response["ok"] is True
    assert response["symbol"] == "TCS"
    assert "announcements" in response["data"]


def test_live_latest_institutional_activity() -> None:
    response = json.loads(tools.institutional_activity.invoke({}))
    assert response["ok"] is True
    assert response["mode"] == "latest"
    assert "fii_dii_cash" in response["data"]


def test_live_india_market_context() -> None:
    response = json.loads(
        tools.india_market_context.invoke(
            {
                "index": "NIFTY 50",
                "commodities": ["CRUDEOIL"],
                "lookback_days": 30,
            }
        )
    )
    assert response["ok"] is True
    assert response["index_name"] == "NIFTY 50"
    assert "price_index" in response["data"]["index"]


def test_live_equity_snapshot_and_history() -> None:
    snapshot = json.loads(tools.nse_equity_snapshot.invoke({"symbol": "TCS"}))
    history = json.loads(
        tools.equity_trading_history.invoke({"symbol": "TCS", "lookback_days": 30})
    )
    assert snapshot["ok"] is True
    assert snapshot["symbol"] == "TCS"
    assert history["ok"] is True
    assert history["data"]["price"]["observations"] > 0


def test_live_market_scan_and_events() -> None:
    scan = json.loads(tools.nse_market_scan.invoke({"index": "NIFTY 50", "limit": 3}))
    events = json.loads(
        tools.equity_event_calendar.invoke(
            {"symbol": "TCS", "lookback_days": 7, "forward_days": 30}
        )
    )
    assert scan["ok"] is True
    assert "breadth" in scan["data"]
    assert events["ok"] is True
    assert "event_calendar" in events["data"]


def test_live_exchange_deals() -> None:
    response = json.loads(
        tools.exchange_deals.invoke(
            {"lookback_days": 7, "deal_types": ["bulk"], "limit_per_type": 3}
        )
    )
    assert response["ok"] is True
    assert "bulk" in response["data"]


def test_live_nifty_derivatives_snapshot() -> None:
    response = json.loads(
        tools.nse_derivatives_snapshot.invoke(
            {"symbol": "NIFTY", "strikes_each_side": 2}
        )
    )
    assert response["ok"] is True
    assert response["data"]["atm_strike"] is not None
    assert len(response["data"]["strikes"]) <= 5

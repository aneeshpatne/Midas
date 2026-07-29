from datetime import date

import pandas as pd
import pytest

from midas import market_data


def test_records_normalizes_dataframe_and_non_finite_values() -> None:
    frame = pd.DataFrame(
        [
            {"date": pd.Timestamp("2026-07-28"), "value": 10.0},
            {"date": pd.NaT, "value": float("nan")},
        ]
    )

    assert market_data.records(frame) == [
        {"date": "2026-07-28T00:00:00", "value": 10.0},
        {"date": None, "value": None},
    ]


def test_summarize_series_sorts_dates_and_computes_drawdown() -> None:
    frame = pd.DataFrame(
        {
            "Date": ["03-01-2026", "01-01-2026", "02-01-2026"],
            "Close": [90, 100, 120],
        }
    )

    summary = market_data.summarize_series(frame, value_columns=("Close",))

    assert summary["observations"] == 3
    assert summary["start_date"] == "2026-01-01"
    assert summary["end_date"] == "2026-01-03"
    assert summary["return_pct"] == pytest.approx(-10.0)
    assert summary["max_drawdown_pct"] == pytest.approx(-25.0)


def test_fetch_institutional_activity_keeps_partial_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nselib import nsdl_fpi
    from nselib.capital_market import capital_market_data

    monkeypatch.setattr(
        capital_market_data,
        "fii_dii_trading_activity",
        lambda: pd.DataFrame([{"category": "FII/FPI", "net": -25.5}]),
    )
    monkeypatch.setattr(
        nsdl_fpi,
        "fetch_nsdl_fpi_latest_investment_activity",
        lambda: pd.DataFrame([{"report_date": "28-Jul-2026", "equity": 10}]),
    )
    monkeypatch.setattr(
        nsdl_fpi,
        "fetch_nsdl_fpi_latest_derivative_activity",
        lambda: (_ for _ in ()).throw(RuntimeError("temporarily unavailable")),
    )

    result = market_data.fetch_institutional_activity(None)

    assert result["mode"] == "latest"
    assert result["data"]["fii_dii_cash"][0]["net"] == -25.5
    assert result["data"]["nsdl_fpi_derivatives"] == []
    assert "temporarily unavailable" in result["warnings"][0]


def test_fetch_historical_institutional_activity_formats_provider_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nselib import derivatives, nsdl_fpi

    seen: list[str] = []

    def fake_report(provider_date: str) -> pd.DataFrame:
        seen.append(provider_date)
        return pd.DataFrame([{"value": 1}])

    monkeypatch.setattr(nsdl_fpi, "fetch_nsdl_fpi_investment_activity", fake_report)
    monkeypatch.setattr(nsdl_fpi, "fetch_nsdl_fpi_derivative_activity", fake_report)
    monkeypatch.setattr(derivatives, "participant_wise_open_interest", fake_report)
    monkeypatch.setattr(derivatives, "participant_wise_trading_volume", fake_report)
    monkeypatch.setattr(derivatives, "fii_derivatives_statistics", fake_report)

    result = market_data.fetch_institutional_activity(date(2026, 7, 28))

    assert seen == ["28-07-2026"] * 5
    assert result["trade_date"] == "2026-07-28"
    assert result["mode"] == "historical"


def test_fetch_market_context_summarizes_and_warns_per_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from indianmarketdata import mcx, nse

    monkeypatch.setattr(
        nse,
        "get_historical_index",
        lambda *_: pd.DataFrame({"Date": ["01-01-2026", "02-01-2026"], "Close": [100, 110]}),
    )
    monkeypatch.setattr(
        nse,
        "get_tri",
        lambda *_: pd.DataFrame(
            {"Date": ["01-01-2026", "02-01-2026"], "Total Returns Index": [200, 224]}
        ),
    )

    def fake_archive(*_args: object, commodity: str) -> pd.DataFrame:
        if commodity == "GOLD":
            raise RuntimeError("archive unavailable")
        return pd.DataFrame(
            {"Date": ["01-01-2026", "02-01-2026"], "Spot Price (Rs.)": [80, 100]}
        )

    monkeypatch.setattr(mcx, "get_spot_archive", fake_archive)
    monkeypatch.setattr(
        mcx,
        "get_spot_recent",
        lambda *, commodity: pd.DataFrame(
            [{"Commodity": commodity, "Spot Price (Rs.)": 100, "Up/Down": 2}]
        ),
    )

    result = market_data.fetch_india_market_context(
        "NIFTY 50", ["CRUDEOIL", "GOLD"], lookback_days=90
    )

    assert result["data"]["index"]["price_index"]["return_pct"] == pytest.approx(10)
    assert result["data"]["index"]["total_return_index"]["return_pct"] == pytest.approx(12)
    assert result["data"]["commodities"]["CRUDEOIL"]["performance"]["return_pct"] == 25
    assert result["data"]["commodities"]["GOLD"] is None
    assert "archive unavailable" in result["warnings"][0]


def test_fetch_market_context_falls_back_to_installed_nse_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from indianmarketdata import mcx, nse

    monkeypatch.setattr(
        nse,
        "get_historical_index",
        lambda *_: (_ for _ in ()).throw(RuntimeError("cloudflare blocked")),
    )
    monkeypatch.setattr(
        market_data,
        "_fetch_nse_index_history",
        lambda *_: pd.DataFrame(
            {
                "EOD_TIMESTAMP": ["01-JAN-2026", "02-JAN-2026"],
                "EOD_CLOSE_INDEX_VAL": [100, 105],
            }
        ),
    )
    monkeypatch.setattr(
        nse,
        "get_tri",
        lambda *_: (_ for _ in ()).throw(RuntimeError("TRI blocked")),
    )
    monkeypatch.setattr(
        mcx,
        "get_spot_archive",
        lambda *_args, **_kwargs: pd.DataFrame(
            {"Date": ["01-01-2026"], "Spot Price (Rs.)": [80]}
        ),
    )
    monkeypatch.setattr(
        mcx,
        "get_spot_recent",
        lambda **_kwargs: pd.DataFrame([{"Commodity": "GOLD", "Spot Price (Rs.)": 80}]),
    )

    result = market_data.fetch_india_market_context(
        "NIFTY 50", ["GOLD"], lookback_days=30
    )

    assert result["data"]["index"]["price_index"]["return_pct"] == pytest.approx(5)
    assert result["data"]["index"]["total_return_index"] is None
    assert "used NSE fallback" in result["warnings"][0]


def test_fetch_nse_equity_snapshot_keeps_identity_when_quote_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nse

    class FakeNSE:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def equityMetaInfo(self, symbol: str) -> dict:
            assert symbol == "TCS"
            return {
                "symbol": "TCS",
                "companyName": "Tata Consultancy Services Limited",
                "isin": "INE467B01029",
                "isFNOSec": True,
            }

        def quote(self, _symbol: str) -> dict:
            raise RuntimeError("quote unavailable")

    monkeypatch.setattr(nse, "NSE", FakeNSE)

    result = market_data.fetch_nse_equity_snapshot("TCS")

    assert result["data"]["identity"]["isin"] == "INE467B01029"
    assert result["data"]["identity"]["is_fno"] is True
    assert result["data"]["quote"] == {}
    assert "quote unavailable" in result["warnings"][0]


def test_fetch_equity_trading_history_computes_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nselib.capital_market import capital_market_data

    monkeypatch.setattr(
        capital_market_data,
        "price_volume_and_deliverable_position_data",
        lambda **_kwargs: pd.DataFrame(
            {
                "Date": ["01-07-2026", "02-07-2026", "03-07-2026"],
                "Close Price": [100, 110, 99],
                "Total Traded Quantity": [1000, 2000, 3000],
                "% Dly Qt to Traded Qty": [40, 50, 60],
            }
        ),
    )

    result = market_data.fetch_equity_trading_history("TCS", lookback_days=30)

    assert result["data"]["price"]["return_pct"] == pytest.approx(-1)
    assert result["data"]["price"]["max_drawdown_pct"] == pytest.approx(-10)
    assert result["data"]["trading_activity"]["average_volume"] == 2000
    assert result["data"]["trading_activity"]["latest_delivery_pct"] == 60
    assert len(result["data"]["latest_observations"]) == 3


def test_fetch_nse_market_scan_summarizes_breadth_and_partial_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nse
    from nselib import capital_market

    class FakeNSE:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def listEquityStocksByIndex(self, *, index: str) -> dict:
            return {
                "timestamp": "now",
                "marketStatus": {"marketStatus": "Open"},
                "data": [
                    {"symbol": index, "pChange": 0},
                    {"symbol": "A", "pChange": 2, "lastPrice": 10},
                    {"symbol": "B", "pChange": -1, "lastPrice": 20},
                    {"symbol": "C", "pChange": 0, "lastPrice": 30},
                ],
            }

        def liveVolumeGainers(self) -> dict:
            raise RuntimeError("volume endpoint unavailable")

    monkeypatch.setattr(nse, "NSE", FakeNSE)
    monkeypatch.setattr(
        capital_market,
        "most_active_equities",
        lambda **_kwargs: pd.DataFrame([{"symbol": "A", "value": 100}]),
    )
    monkeypatch.setattr(
        capital_market,
        "india_vix_data",
        lambda **_kwargs: pd.DataFrame(
            {"TIMESTAMP": ["01-07-2026", "02-07-2026"], "CLOSE": [14, 15]}
        ),
    )

    result = market_data.fetch_nse_market_scan("NIFTY 500", limit=2)

    assert result["data"]["breadth"]["advances"] == 1
    assert result["data"]["breadth"]["declines"] == 1
    assert result["data"]["gainers"][0]["symbol"] == "A"
    assert result["data"]["losers"][0]["symbol"] == "B"
    assert "volume endpoint unavailable" in result["warnings"][0]


def test_event_calendar_and_deals_filter_symbol_and_keep_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nselib import capital_market

    rows = pd.DataFrame(
        [
            {"symbol": "TCS", "event": "Results"},
            {"symbol": "INFY", "event": "Dividend"},
        ]
    )
    monkeypatch.setattr(capital_market, "event_calendar_for_equity", lambda **_kwargs: rows)
    monkeypatch.setattr(capital_market, "corporate_actions_for_equity", lambda **_kwargs: rows)
    monkeypatch.setattr(capital_market, "financial_results_for_equity", lambda **_kwargs: rows)
    monkeypatch.setattr(capital_market, "bulk_deal_data", lambda **_kwargs: rows)
    monkeypatch.setattr(capital_market, "block_deals_data", lambda **_kwargs: rows)
    monkeypatch.setattr(capital_market, "short_selling_data", lambda **_kwargs: rows)

    events = market_data.fetch_equity_event_calendar(
        "TCS", lookback_days=7, forward_days=30, limit=5
    )
    deals = market_data.fetch_exchange_deals(
        "TCS", lookback_days=30, deal_types=["bulk", "short"], limit=5
    )

    assert events["data"]["event_calendar"] == [{"symbol": "TCS", "event": "Results"}]
    assert events["data"]["corporate_actions"][0]["symbol"] == "TCS"
    assert list(deals["data"]) == ["bulk", "short"]
    assert deals["data"]["short"][0]["symbol"] == "TCS"


def test_derivatives_snapshot_calculates_positioning_and_bounds_strikes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nse
    from nselib import derivatives

    expiry = date(2026, 8, 27)

    class FakeNSE:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def optionChain(self, _symbol: str, _expiry=None) -> dict:
            rows = []
            for strike, call_oi, put_oi in (
                (90, 100, 400),
                (100, 300, 300),
                (110, 500, 100),
            ):
                rows.append(
                    {
                        "expiryDates": "27-Aug-2026",
                        "strikePrice": strike,
                        "CE": {
                            "openInterest": call_oi,
                            "changeinOpenInterest": 10,
                            "lastPrice": 1,
                        },
                        "PE": {
                            "openInterest": put_oi,
                            "changeinOpenInterest": 20,
                            "lastPrice": 2,
                        },
                    }
                )
            return {
                "records": {
                    "timestamp": "now",
                    "underlyingValue": 101,
                    "expiryDates": ["27-Aug-2026"],
                    "data": rows,
                }
            }

        def fnoLots(self) -> dict:
            return {"TCS": 175}

    monkeypatch.setattr(nse, "NSE", FakeNSE)
    monkeypatch.setattr(
        derivatives,
        "fno_security_in_ban_period",
        lambda _trade_date: ["OTHER"],
    )

    result = market_data.fetch_nse_derivatives_snapshot(
        "TCS", expiry=expiry, strikes_each_side=1
    )

    assert result["data"]["atm_strike"] == 100
    assert result["data"]["put_call_ratio"] == pytest.approx(800 / 900)
    assert result["data"]["max_call_oi"]["strike"] == 110
    assert result["data"]["max_put_oi"]["strike"] == 90
    assert result["data"]["lot_size"] == 175
    assert result["data"]["in_fno_ban"] is False
    assert len(result["data"]["strikes"]) == 3

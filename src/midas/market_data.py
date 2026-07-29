"""Adapters for unofficial Indian market-data packages.

Provider-specific DataFrames and loosely typed NSE payloads are normalized here
before DeepAgent tools serialize them.  No provider object leaks into the public
tool response.
"""

from __future__ import annotations

import math
import tempfile
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

NSE_FILINGS_URL = "https://www.nseindia.com/companies-listing/corporate-filings"
NSE_FII_DII_URL = "https://www.nseindia.com/reports/fii-dii"
NSE_FNO_REPORTS_URL = "https://www.nseindia.com/all-reports-derivatives"
NSDL_FPI_URL = "https://www.fpi.nsdl.co.in/web/Reports/Latest.aspx"
NIFTY_INDEX_URL = "https://www.niftyindices.com/reports/historical-data"
NSE_INDEX_HISTORY_URL = "https://www.nseindia.com/reports-indices-historical-index-data"
MCX_SPOT_URL = "https://www.mcxindia.com/market-data/spot-market-price"
NSE_QUOTE_URL = "https://www.nseindia.com/get-quotes/equity"
NSE_HISTORICAL_URL = "https://www.nseindia.com/report-detail/eq_security"
NSE_MARKET_URL = "https://www.nseindia.com/market-data/live-equity-market"
NSE_EVENTS_URL = "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar"
NSE_DEALS_URL = "https://www.nseindia.com/report-detail/display-bulk-and-block-deals"
NSE_SHORT_SELLING_URL = "https://www.nseindia.com/report-detail/short-selling"
NSE_OPTION_CHAIN_URL = "https://www.nseindia.com/option-chain"

_EXPECTED_PROVIDER_ERRORS = (
    OSError,
    TimeoutError,
    ConnectionError,
    RuntimeError,
    ValueError,
    KeyError,
    TypeError,
)


def _json_value(value: Any) -> Any:
    """Convert pandas/numpy/datetime values into strict JSON-compatible values."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def records(value: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Normalize a provider DataFrame/list/dict into bounded row dictionaries."""
    if isinstance(value, pd.DataFrame):
        rows = value.to_dict(orient="records")
    elif isinstance(value, list):
        rows = [row for row in value if isinstance(row, dict)]
    elif isinstance(value, dict):
        nested = value.get("data")
        if isinstance(nested, list):
            rows = [row for row in nested if isinstance(row, dict)]
        else:
            rows = [value]
    else:
        rows = []
    if limit is not None:
        rows = rows[:limit]
    return [_json_value(row) for row in rows]


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    """Return the first present, non-null value from a provider mapping."""
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return _json_value(value)
    return None


def _optional_column(frame: pd.DataFrame, *candidates: str) -> str | None:
    try:
        return _find_column(frame, *candidates)
    except KeyError:
        return None


def _filter_symbol_rows(rows: list[dict[str, Any]], symbol: str | None) -> list[dict[str, Any]]:
    if not symbol:
        return rows
    wanted = symbol.casefold()
    symbol_keys = ("symbol", "Symbol", "SYMBOL", "security", "Security Name", "symbol_name")
    return [
        row
        for row in rows
        if any(str(row.get(key, "")).casefold() == wanted for key in symbol_keys)
    ]


def fetch_nse_equity_snapshot(symbol: str) -> dict[str, Any]:
    """Fetch a compact live NSE quote and security identity snapshot."""
    from nse import NSE

    data: dict[str, Any] = {"identity": {}, "quote": {}}
    warnings: list[str] = []
    with tempfile.TemporaryDirectory(prefix="midas-nse-quote-") as tmp:
        with NSE(download_folder=tmp, server=True) as client:
            try:
                meta = client.equityMetaInfo(symbol)
                data["identity"] = {
                    "symbol": _first(meta, "symbol", "symbolName"),
                    "company_name": _first(meta, "companyName", "company_name"),
                    "isin": _first(meta, "isin", "isinCode"),
                    "series": _first(meta, "activeSeries", "series"),
                    "status": _first(meta, "status", "listingStatus"),
                    "is_fno": _first(meta, "isFNOSec", "isFno"),
                    "is_etf": _first(meta, "isETFSec", "isEtf"),
                    "is_suspended": _first(meta, "isSuspended"),
                    "raw_flags": {
                        key: _json_value(value)
                        for key, value in meta.items()
                        if key.startswith("is") and value is not None
                    },
                }
            except _EXPECTED_PROVIDER_ERRORS as exc:
                warnings.append(f"identity: {exc}")

            try:
                quote = client.quote(symbol)
                order_book = quote.get("orderBook") or {}
                trade = quote.get("tradeInfo") or {}
                metadata = quote.get("metaData") or {}
                security = quote.get("securityInfo") or {}
                price_info = quote.get("priceInfo") or {}
                data["quote"] = {
                    "timestamp": _first(quote, "lastUpdateTime", "timestamp"),
                    "last_price": _first(order_book, "lastPrice") or _first(
                        price_info, "lastPrice"
                    ),
                    "change": _first(order_book, "change") or _first(price_info, "change"),
                    "change_pct": _first(order_book, "pChange") or _first(
                        price_info, "pChange"
                    ),
                    "open": _first(metadata, "open") or _first(price_info, "open"),
                    "day_high": _first(metadata, "dayHigh")
                    or _first(price_info, "intraDayHighLow"),
                    "day_low": _first(metadata, "dayLow"),
                    "previous_close": _first(metadata, "previousClose") or _first(
                        price_info, "previousClose"
                    ),
                    "volume": _first(trade, "totalTradedVolume"),
                    "value": _first(trade, "totalTradedValue"),
                    "vwap": _first(trade, "vwap"),
                    "delivery_quantity": _first(trade, "deliveryQuantity"),
                    "delivery_pct": _first(trade, "deliveryToTradedQuantity"),
                    "market_cap": _first(trade, "totalMarketCap"),
                    "price_band": {
                        "lower": _first(security, "lowerPriceBand"),
                        "upper": _first(security, "upperPriceBand"),
                    },
                    "week_52": {
                        "high": _first(security, "weekHighLow")
                        or _first(price_info, "weekHighLow"),
                        "low": _first(security, "weekLow"),
                    },
                    "buy_quantity": _first(order_book, "totalBuyQuantity"),
                    "sell_quantity": _first(order_book, "totalSellQuantity"),
                }
            except _EXPECTED_PROVIDER_ERRORS as exc:
                warnings.append(f"quote: {exc}")

    return {
        "symbol": symbol,
        "fetched_at": datetime.now().astimezone().isoformat(),
        "source_url": f"{NSE_QUOTE_URL}?symbol={symbol}",
        "data": data,
        "warnings": warnings,
    }


def fetch_equity_trading_history(symbol: str, *, lookback_days: int) -> dict[str, Any]:
    """Summarize NSE price, volume, and delivery history for an equity."""
    from nselib.capital_market.capital_market_data import (
        price_volume_and_deliverable_position_data,
    )

    end = date.today()
    start = end - timedelta(days=lookback_days)
    frame = price_volume_and_deliverable_position_data(
        symbol=symbol,
        from_date=start.strftime("%d-%m-%Y"),
        to_date=end.strftime("%d-%m-%Y"),
    )
    if frame.empty:
        raise ValueError("provider returned no trading history")

    date_column = _find_column(frame, "Date", "CH_TIMESTAMP", "TIMESTAMP")
    close_column = _find_column(frame, "Close Price", "CLOSE", "Close")
    volume_column = _optional_column(frame, "Total Traded Quantity", "TOTTRDQTY", "Volume")
    delivery_column = _optional_column(
        frame,
        "% Dly Qt to Traded Qty",
        "DELIV_PER",
        "Delivery Percentage",
    )
    clean = frame.copy()
    clean["_date"] = pd.to_datetime(
        clean[date_column], errors="coerce", format="mixed", dayfirst=True
    )
    clean["_close"] = pd.to_numeric(clean[close_column], errors="coerce")
    clean = clean.dropna(subset=["_date", "_close"]).sort_values("_date")
    if clean.empty:
        raise ValueError("provider returned no usable trading observations")

    price = summarize_series(
        frame,
        value_columns=(close_column,),
        date_columns=(date_column,),
    )
    returns = clean["_close"].pct_change().dropna()
    price["annualized_volatility_pct"] = (
        float(returns.std(ddof=1) * math.sqrt(252) * 100) if len(returns) > 1 else None
    )

    activity: dict[str, Any] = {}
    if volume_column:
        volumes = pd.to_numeric(clean[volume_column], errors="coerce")
        recent = volumes.tail(min(20, len(volumes)))
        activity["average_volume"] = _json_value(volumes.mean())
        activity["recent_average_volume"] = _json_value(recent.mean())
        activity["latest_volume"] = _json_value(volumes.iloc[-1])
        activity["latest_vs_recent_average"] = (
            _json_value(volumes.iloc[-1] / recent.mean()) if recent.mean() else None
        )
    if delivery_column:
        delivery = pd.to_numeric(clean[delivery_column], errors="coerce")
        first_half = delivery.iloc[: max(1, len(delivery) // 2)].mean()
        second_half = delivery.iloc[max(1, len(delivery) // 2) :].mean()
        activity["average_delivery_pct"] = _json_value(delivery.mean())
        activity["latest_delivery_pct"] = _json_value(delivery.iloc[-1])
        activity["delivery_trend_change_pct_points"] = _json_value(second_half - first_half)

    compact_columns = [date_column, close_column]
    if volume_column:
        compact_columns.append(volume_column)
    if delivery_column:
        compact_columns.append(delivery_column)
    latest = records(frame.sort_values(date_column).tail(10)[compact_columns])
    return {
        "symbol": symbol,
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "fetched_at": datetime.now().astimezone().isoformat(),
        "source_url": f"{NSE_HISTORICAL_URL}?symbol={symbol}",
        "data": {"price": price, "trading_activity": activity, "latest_observations": latest},
        "warnings": [],
    }


def fetch_nse_company_filings(
    symbol: str,
    *,
    lookback_days: int,
    limit_per_section: int,
) -> dict[str, Any]:
    """Fetch several company-level NSE filing feeds with partial-failure handling."""
    from nse import NSE

    end = datetime.combine(date.today(), datetime.min.time())
    start = end - timedelta(days=lookback_days)
    data: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []

    with tempfile.TemporaryDirectory(prefix="midas-nse-filings-") as tmp:
        with NSE(download_folder=tmp, server=True) as client:
            calls: tuple[tuple[str, Callable[[], Any]], ...] = (
                (
                    "announcements",
                    lambda: client.announcements(
                        symbol=symbol, from_date=start, to_date=end
                    ),
                ),
                (
                    "corporate_actions",
                    lambda: client.actions(symbol=symbol, from_date=start, to_date=end),
                ),
                (
                    "board_meetings",
                    lambda: client.boardMeetings(
                        symbol=symbol, from_date=start, to_date=end
                    ),
                ),
                (
                    "financial_result_filings",
                    lambda: client.financial_results(
                        symbol=symbol, from_date=start, to_date=end
                    ),
                ),
                ("results_comparison", lambda: client.results_comparison(symbol)),
                ("shareholding", lambda: client.shareholding(symbol)),
                ("annual_reports", lambda: client.annual_reports(symbol)),
            )
            for section, call in calls:
                try:
                    payload = call()
                    if section == "results_comparison" and isinstance(payload, dict):
                        payload = payload.get("resCmpData") or []
                    data[section] = records(payload, limit=limit_per_section)
                except _EXPECTED_PROVIDER_ERRORS as exc:
                    data[section] = []
                    warnings.append(f"{section}: {exc}")

    return {
        "symbol": symbol,
        "from_date": start.date().isoformat(),
        "to_date": end.date().isoformat(),
        "fetched_at": datetime.now().astimezone().isoformat(),
        "source_url": f"{NSE_FILINGS_URL}?symbol={symbol}",
        "data": data,
        "warnings": warnings,
    }


def fetch_institutional_activity(trade_date: date | None) -> dict[str, Any]:
    """Fetch latest or date-specific institutional cash and derivatives reports."""
    from nselib import derivatives, nsdl_fpi
    from nselib.capital_market.capital_market_data import fii_dii_trading_activity

    sections: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    if trade_date is None:
        calls: tuple[tuple[str, Callable[[], Any]], ...] = (
            ("fii_dii_cash", fii_dii_trading_activity),
            (
                "nsdl_fpi_investment",
                nsdl_fpi.fetch_nsdl_fpi_latest_investment_activity,
            ),
            (
                "nsdl_fpi_derivatives",
                nsdl_fpi.fetch_nsdl_fpi_latest_derivative_activity,
            ),
        )
    else:
        provider_date = trade_date.strftime("%d-%m-%Y")
        calls = (
            (
                "nsdl_fpi_investment",
                lambda: nsdl_fpi.fetch_nsdl_fpi_investment_activity(provider_date),
            ),
            (
                "nsdl_fpi_derivatives",
                lambda: nsdl_fpi.fetch_nsdl_fpi_derivative_activity(provider_date),
            ),
            (
                "participant_open_interest",
                lambda: derivatives.participant_wise_open_interest(provider_date),
            ),
            (
                "participant_trading_volume",
                lambda: derivatives.participant_wise_trading_volume(provider_date),
            ),
            (
                "fii_derivatives_statistics",
                lambda: derivatives.fii_derivatives_statistics(provider_date),
            ),
        )

    for section, call in calls:
        try:
            sections[section] = records(call(), limit=50)
        except _EXPECTED_PROVIDER_ERRORS as exc:
            sections[section] = []
            warnings.append(f"{section}: {exc}")

    return {
        "trade_date": trade_date.isoformat() if trade_date else None,
        "mode": "historical" if trade_date else "latest",
        "fetched_at": datetime.now().astimezone().isoformat(),
        "source_urls": [NSE_FII_DII_URL, NSDL_FPI_URL, NSE_FNO_REPORTS_URL],
        "data": sections,
        "warnings": warnings,
    }


def _find_column(frame: pd.DataFrame, *candidates: str) -> str:
    normalized = {
        "".join(character for character in str(column).casefold() if character.isalnum()): column
        for column in frame.columns
    }
    for candidate in candidates:
        key = "".join(character for character in candidate.casefold() if character.isalnum())
        if key in normalized:
            return str(normalized[key])
    raise KeyError(f"Expected one of these columns: {', '.join(candidates)}")


def summarize_series(
    frame: pd.DataFrame,
    *,
    value_columns: tuple[str, ...],
    date_columns: tuple[str, ...] = ("Date",),
) -> dict[str, Any]:
    """Return an agent-sized performance summary for a dated numeric series."""
    if frame.empty:
        raise ValueError("provider returned no observations")
    date_column = _find_column(frame, *date_columns)
    value_column = _find_column(frame, *value_columns)
    clean = pd.DataFrame(
        {
            "date": pd.to_datetime(
                frame[date_column], errors="coerce", format="mixed", dayfirst=True
            ),
            "value": pd.to_numeric(frame[value_column], errors="coerce"),
        }
    ).dropna()
    clean = clean.sort_values("date").drop_duplicates("date", keep="last")
    if clean.empty:
        raise ValueError("provider returned no usable dated numeric observations")

    first = float(clean["value"].iloc[0])
    last = float(clean["value"].iloc[-1])
    running_high = clean["value"].cummax()
    drawdowns = clean["value"].div(running_high).sub(1).mul(100)
    return {
        "value_field": value_column,
        "observations": len(clean),
        "start_date": clean["date"].iloc[0].date().isoformat(),
        "end_date": clean["date"].iloc[-1].date().isoformat(),
        "start_value": first,
        "end_value": last,
        "return_pct": ((last / first) - 1) * 100 if first else None,
        "high": float(clean["value"].max()),
        "low": float(clean["value"].min()),
        "max_drawdown_pct": float(drawdowns.min()),
    }


def _fetch_nse_index_history(index: str, start: date, end: date) -> pd.DataFrame:
    """Fallback price-index history using the already installed NSE client."""
    from nse import NSE

    with tempfile.TemporaryDirectory(prefix="midas-nse-index-") as tmp:
        with NSE(download_folder=tmp, server=True) as client:
            rows = client.fetch_historical_index_data(index, start, end)
    return pd.DataFrame(rows)


def fetch_india_market_context(
    index: str,
    commodities: list[str],
    *,
    lookback_days: int,
) -> dict[str, Any]:
    """Fetch compact Nifty price/TRI and MCX commodity performance context."""
    from indianmarketdata import mcx, nse

    end = date.today()
    start = end - timedelta(days=lookback_days)
    nifty_start = start.strftime("%d-%b-%Y")
    nifty_end = end.strftime("%d-%b-%Y")
    data: dict[str, Any] = {"index": {}, "commodities": {}}
    warnings: list[str] = []

    try:
        try:
            price_history = nse.get_historical_index(index, nifty_start, nifty_end)
            price_value_columns = ("Close", "Closing Index Value")
            price_date_columns = ("Date",)
        except _EXPECTED_PROVIDER_ERRORS as primary_exc:
            price_history = _fetch_nse_index_history(index, start, end)
            price_value_columns = ("EOD_CLOSE_INDEX_VAL", "Close")
            price_date_columns = ("EOD_TIMESTAMP", "Date")
            warnings.append(
                f"price_index: used NSE fallback after NiftyIndices error: {primary_exc}"
            )
        data["index"]["price_index"] = summarize_series(
            price_history,
            value_columns=price_value_columns,
            date_columns=price_date_columns,
        )
    except _EXPECTED_PROVIDER_ERRORS as exc:
        data["index"]["price_index"] = None
        warnings.append(f"price_index: {exc}")

    try:
        data["index"]["total_return_index"] = summarize_series(
            nse.get_tri(index, nifty_start, nifty_end),
            value_columns=("Total Returns Index", "TRI"),
        )
    except _EXPECTED_PROVIDER_ERRORS as exc:
        data["index"]["total_return_index"] = None
        warnings.append(f"total_return_index: {exc}")

    for commodity in commodities:
        try:
            history = mcx.get_spot_archive(
                start.isoformat(), end.isoformat(), commodity=commodity
            )
            summary = summarize_series(
                history,
                value_columns=("Spot Price (Rs.)", "Spot Price"),
            )
            latest = records(mcx.get_spot_recent(commodity=commodity), limit=5)
            data["commodities"][commodity] = {"performance": summary, "latest": latest}
        except _EXPECTED_PROVIDER_ERRORS as exc:
            data["commodities"][commodity] = None
            warnings.append(f"{commodity}: {exc}")

    return {
        "index_name": index,
        "commodities_requested": commodities,
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "fetched_at": datetime.now().astimezone().isoformat(),
        "source_urls": [NIFTY_INDEX_URL, NSE_INDEX_HISTORY_URL, MCX_SPOT_URL],
        "data": data,
        "warnings": warnings,
    }


def _compact_market_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": _first(row, "symbol", "symbolName"),
        "company_name": _first(row.get("meta") or {}, "companyName", "company_name"),
        "last_price": _first(row, "lastPrice", "ltp"),
        "change_pct": _first(row, "pChange", "perChange"),
        "volume": _first(row, "totalTradedVolume", "quantityTraded"),
        "value": _first(row, "totalTradedValue", "turnover"),
    }


def fetch_nse_market_scan(index: str, *, limit: int) -> dict[str, Any]:
    """Fetch compact breadth, movers, activity, and volatility context."""
    from nse import NSE
    from nselib import capital_market

    data: dict[str, Any] = {}
    warnings: list[str] = []
    with tempfile.TemporaryDirectory(prefix="midas-nse-scan-") as tmp:
        with NSE(download_folder=tmp, server=True) as client:
            try:
                index_payload = client.listEquityStocksByIndex(index=index)
                members = [
                    row
                    for row in index_payload.get("data") or []
                    if isinstance(row, dict)
                    and str(row.get("symbol", "")).casefold() != index.casefold()
                ]
                changes = [
                    float(row["pChange"])
                    for row in members
                    if isinstance(row.get("pChange"), (int, float))
                ]
                data["breadth"] = {
                    "advances": sum(value > 0 for value in changes),
                    "declines": sum(value < 0 for value in changes),
                    "unchanged": sum(value == 0 for value in changes),
                    "advance_decline_ratio": (
                        sum(value > 0 for value in changes) / sum(value < 0 for value in changes)
                        if sum(value < 0 for value in changes)
                        else None
                    ),
                    "timestamp": index_payload.get("timestamp"),
                    "market_status": (index_payload.get("marketStatus") or {}).get(
                        "marketStatus"
                    ),
                }
                gainers = [row for row in members if (row.get("pChange") or 0) > 0]
                losers = [row for row in members if (row.get("pChange") or 0) < 0]
                data["gainers"] = [
                    _compact_market_row(row)
                    for row in sorted(
                        gainers, key=lambda item: item.get("pChange") or 0, reverse=True
                    )[:limit]
                ]
                data["losers"] = [
                    _compact_market_row(row)
                    for row in sorted(losers, key=lambda item: item.get("pChange") or 0)[
                        :limit
                    ]
                ]
            except _EXPECTED_PROVIDER_ERRORS as exc:
                warnings.append(f"index_breadth_and_movers: {exc}")

            try:
                rows = (client.liveVolumeGainers().get("data") or [])[:limit]
                data["volume_gainers"] = [
                    _compact_market_row(row) for row in rows if isinstance(row, dict)
                ]
            except _EXPECTED_PROVIDER_ERRORS as exc:
                warnings.append(f"volume_gainers: {exc}")

    try:
        active = capital_market.most_active_equities(fetch_by="value")
        data["most_active"] = records(active, limit=limit)
    except _EXPECTED_PROVIDER_ERRORS as exc:
        warnings.append(f"most_active: {exc}")
    try:
        vix = capital_market.india_vix_data(period="1M")
        data["india_vix"] = summarize_series(
            vix,
            value_columns=("CLOSE", "Close", "Closing Price"),
            date_columns=("TIMESTAMP", "Date"),
        )
    except _EXPECTED_PROVIDER_ERRORS as exc:
        warnings.append(f"india_vix: {exc}")

    return {
        "index_name": index,
        "fetched_at": datetime.now().astimezone().isoformat(),
        "source_urls": [f"{NSE_MARKET_URL}?symbol={index.replace(' ', '%20')}"],
        "data": data,
        "warnings": warnings,
    }


def fetch_equity_event_calendar(
    symbol: str | None,
    *,
    lookback_days: int,
    forward_days: int,
    limit: int,
) -> dict[str, Any]:
    """Fetch market-wide or symbol-filtered corporate events."""
    from nselib import capital_market

    today = date.today()
    start = today - timedelta(days=lookback_days)
    end = today + timedelta(days=forward_days)
    start_text = start.strftime("%d-%m-%Y")
    end_text = end.strftime("%d-%m-%Y")
    data: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    calls: tuple[tuple[str, Callable[[], Any]], ...] = (
        (
            "event_calendar",
            lambda: capital_market.event_calendar_for_equity(
                from_date=start_text, to_date=end_text
            ),
        ),
        (
            "corporate_actions",
            lambda: capital_market.corporate_actions_for_equity(
                from_date=start_text, to_date=end_text
            ),
        ),
        (
            "financial_results",
            lambda: capital_market.financial_results_for_equity(
                from_date=start_text, to_date=end_text
            ),
        ),
    )
    for section, call in calls:
        try:
            data[section] = _filter_symbol_rows(records(call()), symbol)[:limit]
        except _EXPECTED_PROVIDER_ERRORS as exc:
            data[section] = []
            warnings.append(f"{section}: {exc}")
    return {
        "symbol": symbol,
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "fetched_at": datetime.now().astimezone().isoformat(),
        "source_url": NSE_EVENTS_URL,
        "data": data,
        "warnings": warnings,
    }


def fetch_exchange_deals(
    symbol: str | None,
    *,
    lookback_days: int,
    deal_types: list[str],
    limit: int,
) -> dict[str, Any]:
    """Fetch and normalize NSE bulk, block, and short-selling reports."""
    from nselib import capital_market

    end = date.today()
    start = end - timedelta(days=lookback_days)
    start_text = start.strftime("%d-%m-%Y")
    end_text = end.strftime("%d-%m-%Y")
    providers: dict[str, Callable[[], Any]] = {
        "bulk": lambda: capital_market.bulk_deal_data(
            from_date=start_text, to_date=end_text
        ),
        "block": lambda: capital_market.block_deals_data(
            from_date=start_text, to_date=end_text
        ),
        "short": lambda: capital_market.short_selling_data(
            from_date=start_text, to_date=end_text
        ),
    }
    data: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    for deal_type in deal_types:
        try:
            data[deal_type] = _filter_symbol_rows(records(providers[deal_type]()), symbol)[
                :limit
            ]
        except _EXPECTED_PROVIDER_ERRORS as exc:
            data[deal_type] = []
            warnings.append(f"{deal_type}: {exc}")
    return {
        "symbol": symbol,
        "deal_types": deal_types,
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "fetched_at": datetime.now().astimezone().isoformat(),
        "source_urls": [NSE_DEALS_URL, NSE_SHORT_SELLING_URL],
        "data": data,
        "warnings": warnings,
    }


def _option_max_pain(rows: list[dict[str, Any]]) -> float | None:
    strikes = sorted(
        {
            float(row["strikePrice"])
            for row in rows
            if isinstance(row.get("strikePrice"), (int, float))
        }
    )
    if not strikes:
        return None
    payouts: dict[float, float] = {}
    for settlement in strikes:
        total = 0.0
        for row in rows:
            strike = float(row.get("strikePrice") or 0)
            call_oi = float((row.get("CE") or {}).get("openInterest") or 0)
            put_oi = float((row.get("PE") or {}).get("openInterest") or 0)
            total += max(0.0, settlement - strike) * call_oi
            total += max(0.0, strike - settlement) * put_oi
        payouts[settlement] = total
    return min(payouts, key=payouts.get)


def fetch_nse_derivatives_snapshot(
    symbol: str,
    *,
    expiry: date | None,
    strikes_each_side: int,
) -> dict[str, Any]:
    """Summarize an NSE option chain plus contract and ban-status context."""
    from nse import NSE
    from nselib import derivatives

    warnings: list[str] = []
    with tempfile.TemporaryDirectory(prefix="midas-nse-options-") as tmp:
        with NSE(download_folder=tmp, server=True) as client:
            raw = client.optionChain(
                symbol.lower(),
                datetime.combine(expiry, datetime.min.time()) if expiry else None,
            )
            expiry_values = (raw.get("records") or {}).get("expiryDates") or []
            expiry_label = (
                expiry.strftime("%d-%b-%Y")
                if expiry
                else (expiry_values[0] if expiry_values else None)
            )
            if not expiry_label:
                raise ValueError("provider returned no valid option expiry")
            rows = [
                row
                for row in (raw.get("records") or {}).get("data") or []
                if row.get("expiryDates") == expiry_label
            ]
            if not rows:
                raise ValueError(f"provider returned no option rows for {expiry_label}")
            underlying = (raw.get("records") or {}).get("underlyingValue")
            strikes = sorted(float(row["strikePrice"]) for row in rows)
            atm = min(strikes, key=lambda value: abs(value - float(underlying or value)))
            atm_index = strikes.index(atm)
            selected_strikes = set(
                strikes[
                    max(0, atm_index - strikes_each_side) : atm_index + strikes_each_side + 1
                ]
            )

            compact: list[dict[str, Any]] = []
            call_total = put_total = 0.0
            call_change_total = put_change_total = 0.0
            call_max: tuple[float, float] = (0, 0)
            put_max: tuple[float, float] = (0, 0)
            for row in rows:
                strike = float(row["strikePrice"])
                call = row.get("CE") or {}
                put = row.get("PE") or {}
                call_oi = float(call.get("openInterest") or 0)
                put_oi = float(put.get("openInterest") or 0)
                call_change = float(call.get("changeinOpenInterest") or 0)
                put_change = float(put.get("changeinOpenInterest") or 0)
                call_total += call_oi
                put_total += put_oi
                call_change_total += call_change
                put_change_total += put_change
                if call_oi > call_max[1]:
                    call_max = (strike, call_oi)
                if put_oi > put_max[1]:
                    put_max = (strike, put_oi)
                if strike in selected_strikes:
                    compact.append(
                        {
                            "strike": strike,
                            "call": {
                                "oi": call_oi,
                                "change_oi": call_change,
                                "volume": _first(call, "totalTradedVolume"),
                                "iv": _first(call, "impliedVolatility"),
                                "last_price": _first(call, "lastPrice"),
                            },
                            "put": {
                                "oi": put_oi,
                                "change_oi": put_change,
                                "volume": _first(put, "totalTradedVolume"),
                                "iv": _first(put, "impliedVolatility"),
                                "last_price": _first(put, "lastPrice"),
                            },
                        }
                    )
            try:
                lot_size = client.fnoLots().get(symbol.upper())
            except _EXPECTED_PROVIDER_ERRORS as exc:
                lot_size = None
                warnings.append(f"lot_size: {exc}")

    try:
        ban_symbols = derivatives.fno_security_in_ban_period(date.today().strftime("%d-%m-%Y"))
        in_ban = symbol.upper() in {str(item).upper() for item in ban_symbols}
    except _EXPECTED_PROVIDER_ERRORS as exc:
        in_ban = None
        warnings.append(f"fno_ban: {exc}")

    return {
        "symbol": symbol,
        "expiry": expiry_label,
        "fetched_at": datetime.now().astimezone().isoformat(),
        "source_url": f"{NSE_OPTION_CHAIN_URL}?symbol={symbol}",
        "data": {
            "timestamp": (raw.get("records") or {}).get("timestamp"),
            "underlying": underlying,
            "atm_strike": atm,
            "put_call_ratio": put_total / call_total if call_total else None,
            "change_oi_put_call_ratio": (
                put_change_total / call_change_total if call_change_total else None
            ),
            "max_pain": _option_max_pain(rows),
            "max_call_oi": {"strike": call_max[0], "open_interest": call_max[1]},
            "max_put_oi": {"strike": put_max[0], "open_interest": put_max[1]},
            "lot_size": lot_size,
            "in_fno_ban": in_ban,
            "strikes": compact,
        },
        "warnings": warnings,
    }

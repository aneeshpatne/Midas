# MCPs

The only allowed external tools are the MCPs from `src/midas/mcp_server.py`
(`midas-mcp` / server name `midas-market`). Call them by these names only:

| MCP |
| --- |
| `company_fundamentals` |
| `earnings_transcripts` |
| `market_signals` |
| `nse_list_index` |
| `nse_company_filings` |
| `nse_equity_snapshot` |
| `equity_trading_history` |
| `nse_market_scan` |
| `equity_event_calendar` |
| `exchange_deals` |
| `nse_derivatives_snapshot` |
| `institutional_activity` |
| `india_market_context` |

Hosts may add a server prefix (for example `midas__company_fundamentals`); the tool
name is still one of the rows above.

Rules:

- Use **only** these MCPs. No other tools.
- Run them **one at a time**. If a call returns `busy` / `retryable`, wait and retry.
- Check `ok` on the JSON payload before trusting data.
- If an MCP cannot supply a decision-material fact, write `Insufficient Evidence`.
  Never invent numbers, prices, dates, or sources.

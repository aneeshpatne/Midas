# Tools and MCPs

Midas research agents have two complementary surfaces that expose the **same**
capabilities:

1. **In-process LangChain tools** on the DeepAgent graph (`MIDAS_TOOLS` in
   `src/midas/deepagents/tools.py` + `db_tools.py`).
2. **stdio MCP servers** for external hosts:
   - `equity-data-mcp` — market-info scrape tools (`src/midas/mcp_server.py`)
   - `midas-db-mcp` — paper portfolios + research runs (`src/midas/db_mcp_server.py`)

## Market-info tools (scrape / NSE)

| Tool |
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

Also available on DeepAgents (not on equity-data-mcp): `web_research`, `twitter_search`,
chart generators, `send_update`.

Rules:

- Run market scrape tools **one at a time**. If a call returns `busy` / `retryable`, wait and retry.
- Check `ok` on the JSON payload before trusting data.
- If a tool cannot supply a decision-material fact, write `Insufficient Evidence`.
  Never invent numbers, prices, dates, or sources.

## Midas DB tools (durable research + paper portfolio)

| Area | Tools |
| --- | --- |
| Research runs | `research_run_create`, `research_run_get`, `research_run_get_bundle`, `research_run_list`, `research_run_set_mandate`, `research_run_set_report`, `research_run_complete`, `research_run_set_status`, `research_run_update`, `research_run_delete` |
| Run contents | `research_security_add`, `research_security_list`, `research_security_remove`, `research_evidence_append`, `research_evidence_append_many`, `research_evidence_list`, `research_link_portfolio`, `research_links_by_*`, `research_unlink_portfolio` |
| Master data | `company_*`, `security_*` |
| Paper portfolio | `portfolio_*`, `account_*`, `investment_case_*`, `thesis_revision_*`, `transaction_*`, `market_price_*` |
| Trade proposals | `trade_proposal_create`, `trade_proposal_get`, `trade_proposal_list`, `trade_proposal_approve`, `trade_proposal_reject`, `trade_proposal_supersede`, `trade_proposal_execute` |

Rules:

- **One research run per request.** Keep the returned `research_run_id` for every write.
- Persist stage work with `research_evidence_append` (`record_type` values such as
  `mandate`, `universe`, `primary_screen`, `equal_depth`, `ic_decision`, `source`,
  `calculation`).
- Final deliverable is **DB only**: `research_run_set_report` + `research_run_complete`.
  Do **not** create final PDF/HTML or required intermediate Markdown files.
- Paper-portfolio tools are for explicit portfolio work; do not invent trades.
- **BUY/SELL only through trade proposals:** `trade_proposal_create` → user
  approves that exact proposal ID → `trade_proposal_approve` →
  `trade_proposal_execute`. `transaction_create` rejects direct BUY/SELL.

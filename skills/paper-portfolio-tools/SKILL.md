---
name: paper-portfolio-tools
description: >
  Shared portfolio price, benchmark, classification, cost, research-bridge,
  and Midas DB persistence rules. Load with every named paper-portfolio
  action. Not a standalone action.
metadata:
  short-description: "Shared portfolio retrieval and DB rules"
user-invocable: false
disable-model-invocation: true
---
# Portfolio tools and provenance

Use the existing Midas and native-web rules in `skills/equity-research-tools/SKILL.md` for company
research. Portfolio work adds point-in-time price, benchmark, classification,
transaction-cost, transaction, thesis, and DB-state requirements.

## Retrieval and freshness

- Use `nse_equity_snapshot` and `equity_trading_history` for the structured
  price baseline. Use exchange/issuer sources to resolve corporate actions and
  dividends. Store the actual returned timestamp, basis, source URL, and error.
- Use official index-provider TRI data for NIFTY 500, NIFTY 100, NIFTY Midcap
  150, and NIFTY Smallcap 250. Never compare a portfolio total return with a
  price-only index.
- Use the applicable dated AMFI/SEBI market-cap classification or an explicitly
  documented equivalent. Sector mappings require a source and vintage.
- Retrieve official current delivery levies and transaction taxes when a
  proposal is created or refreshed. Keep the policy slippage assumption
  separate from statutory charges. Do not include personal tax.
- A current snapshot is manual and cut-off-bound. Persist source-dated prices
  through the midas-db-mcp market-price tools when applicable.

Store decision-used source metadata in the relevant DB transaction, price,
thesis, investment-case, portfolio, or research-link record. A failed or thin
retrieval is a visible gap, never a price of zero or proof that no event occurred.

## Research bridge

When a portfolio action needs company research, create a fresh isolated Midas
DB research run (`research_run_create`) using the equity router and the
portfolio's rolling five-year horizon. The research run receives
company/universe, horizon, cut-off, and research-relevant constraints only; it
cannot read the portfolio or prior research.

After that run validates (`research_run_complete`), the portfolio layer may
ingest its exact `research_run` id, decision, confidence, price/evidence
condition, thesis, invalidation triggers, and cut-off, and record the bridge
with `research_link_portfolio` (role `ADMISSION`, `THESIS_VALIDATION`, etc.).
Do not scan filesystem `research/`, copy another run's evidence ledger, or let
old conclusions enter fresh research. Cross-date comparison uses the compact
thesis snapshot already stored on the investment case / thesis revisions.

For validation of several holdings, execute one fresh single-stock run per
holding so every selected holding receives focused depth. Run them linearly
when the required worker runtime is unavailable. Record every exact research
run id.

## DB persistence and derived views

Use only the exposed midas-db-mcp tools and their schemas. Resolve securities
through the security/company tools; persist portfolio metadata and policy text
through portfolio tools; funding and executions through transaction tools;
prices through market-price tools; and theses through investment-case and
thesis-revision tools. Link completed research by exact run id with
`research_link_portfolio`.

Derive holdings, cash, performance, allocation, exposure, and warnings from DB
records at request time. Intermediate read models and calculation files are
allowed. The final accepted state must be persisted in Midas DB; do not treat
a workbook, spreadsheet, Markdown file, PDF, or other filesystem artifact as
the canonical deliverable.

## Proposal and execution tools

Persist paper-trade drafts with `trade_proposal_create`; inspect them with
`trade_proposal_get` / `trade_proposal_list`. After explicit user approval that
names the exact proposal ID, record it with `trade_proposal_approve` and execute
it once with `trade_proposal_execute`. Use `trade_proposal_reject` or
`trade_proposal_supersede` for unaccepted drafts. `transaction_create` is for
cash and non-trade ledger events and must not be used directly for BUY or SELL.

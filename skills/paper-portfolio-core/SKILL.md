---
name: paper-portfolio-core
description: >
  Shared paper-portfolio policy, accounting, approvals, thesis states, and
  completion checks. Load with every named paper-portfolio action. Not a
  standalone action.
metadata:
  short-description: "Shared paper-portfolio standard"
user-invocable: false
disable-model-invocation: true
---
# Persistent paper-portfolio standard

Maintain named, long-only Indian listed-equity paper portfolios whose results
can be audited against the research that admitted each holding. This layer is
persistent account state, not a broker connection and not personalized advice.

## Portfolio authority (Midas DB)

Each portfolio is a Midas DB record (plus related tables), accessed through
the midas-db-mcp. Canonical state includes:

```text
portfolios                  — identity, strategy notes, target_capital_paise
portfolio_accounts          — brokerage/cash accounts
transactions                — cash + trade ledger (signed cash_effect_paise)
investment_cases            — thesis shell per security
thesis_revisions            — versioned thesis text
research_portfolio_links    — optional links to completed research runs
```

Temporary working folders are allowed, but do not resolve or identify a
portfolio by scanning directories. Require its DB name or id when identity is
ambiguous.

The transaction ledger is append-only for cash and trades. Correct errors with
offsetting or correcting transactions, not silent mutation of history. Research
admission links are optional and explicit (`research_link_portfolio`).

## Default Moderate policy

Unless the creation prompt overrides a field, record these defaults explicitly:

- strategy label `Moderate` with the explanation: a long-horizon direct-equity
  portfolio seeking durable compounding with controlled exposure across market
  capitalizations;
- Indian listed equity only, INR, paper trading, whole shares, long-only, no
  leverage, derivatives, shorting, or fractional holdings;
- rolling five-year investment horizon;
- invested-equity targets of 60% large-cap, 25% mid-cap, and 15% small-cap;
- tactical cash range 0–20%; the market-cap targets exclude cash;
- soft warnings above 10% for one stock and 25% for one sector;
- no hard stock or sector cap: a warned exposure is permitted only when the
  proposal states its rationale and incremental permanent-loss risk;
- NIFTY 500 TRI as the primary portfolio benchmark, with NIFTY 100 TRI, NIFTY
  Midcap 150 TRI, and NIFTY Smallcap 250 TRI as sleeve references;
- new purchases require a current, exact-run-id-linked `Investable Now` research
  decision. Do not force investment when qualifying research is insufficient;
  preserve cash and show the resulting allocation gap;
- transaction costs use dated delivery charges and transaction taxes plus a
  configurable 10 basis points of slippage per side. Exclude personal income
  and capital-gains tax.

Preserve the creation prompt and its parsed selection mandate in the Midas DB
portfolio description/strategy fields (or dedicated policy records when the
exposed MCP provides them): starting capital, market-cap scope, optional
sector/company scope, custom risk rules, `research_first: true`, and
`proposal_first: true`.
The cash ledger remains authoritative for contributed capital. A restricted
prompt such as “large cap only” overrides the default market-cap mix to
100%/0%/0% and constrains research to that scope; do not quietly add other
buckets to fill the account.

Market-cap and sector definitions are point-in-time inputs. Record the
classification authority, vintage, source URL, and access time. Never silently
reclassify historical snapshots using a later classification.

## Approvals and policy changes

Creation, capital additions, and rebalances may create proposals. A proposal
does not alter cash or holdings. Only an explicit user approval naming the
proposal ID authorizes `trade_execution` events. Refresh stale prices before
execution when the proposal price is no longer from the latest completed
trading session; never backdate a paper execution.

A rebalance cannot change risk appetite, horizon, asset scope, allocation
targets, cash policy, warning thresholds, benchmark, or admission standard.
Only the policy-amendment skill may do so. It increments `policy_version`
and appends the complete old/new changed values to the ledger.

## Accounting and state

Replay accepted events in effective-time order, then recorded-time and event-ID
order as deterministic tie-breakers. Reject duplicate IDs and an execution
without one live approved proposal. Proposals have `Draft`, `Approved`,
`Rejected`, `Superseded`, or `Executed` status.

- Contributions increase cash; withdrawals reduce cash and cannot make it
  negative.
- Buys reduce cash by gross consideration plus costs. Sells increase cash by
  proceeds net of costs. Quantities must be positive whole numbers.
- Use FIFO lots for realized P&L. Display open-position invested price as total
  remaining lot cost divided by remaining shares.
- Capitalize buy-side transaction costs into lot cost; deduct sell-side costs
  from realized proceeds.
- Dividends increase cash on the recorded payment date. Corporate actions must
  preserve an explicit before/after share and cost-basis reconciliation.
- A price snapshot never changes quantity or cost basis. Unknown prices remain
  unknown; never substitute zero.

Derive the current portfolio view from Midas DB records at request time. It
contains portfolio metadata, policy version, cut-off, capital flows, cash,
holdings, performance, market-cap and sector summaries, thesis status,
warnings, sources, and validation status. Each holding contains symbol,
legal name, sector, market-cap bucket/vintage, shares, open cost, invested
price, current price/date/source, market value, absolute and percentage change,
realized and unrealized P&L, portfolio weight, thesis status/date, and exact
research run reference.

Calculate both money-weighted XIRR and cash-flow-neutral time-weighted return
when sufficient observations exist. Guard invalid cash-flow patterns and label
the result unavailable rather than emitting a spreadsheet error. Compare
portfolio TWR with like-for-like TRI over identical dates. Record dividends and
corporate actions before computing the affected period return.

## Thesis states and portfolio warnings

Thesis validation assigns exactly one state:

- `Intact` — current evidence and valuation still support the stored thesis;
- `Weakened` — the thesis remains plausible but a material assumption or
  expected return deteriorated;
- `Broken` — a stored invalidation trigger fired or fresh research no longer
  supports ownership;
- `Needs Evidence` — a decision-critical current fact cannot be resolved.

These states do not trade automatically. `Weakened`, `Broken`, and
`Needs Evidence` must appear on the Overview and in the next rebalance.

Warnings include stock and sector concentration, cash outside policy, market-
cap drift, stale/missing prices, stale/missing research, non-intact theses,
liquidity concerns, allocation gaps, and failed reconciliation. Soft warnings
require explanation but are not automatic vetoes. Hard validation failures are
limited to invalid identity, unsupported instrument, negative cash, unapproved
execution, invalid quantity, missing execution price/source, duplicate event,
or irreconcilable accounting.

## Completion checks

Before publishing an updated portfolio:

1. Validate portfolio, account, transaction, investment-case, thesis, price,
   and research-link records against the exposed midas-db-mcp schemas.
2. Read the DB ledger and reconcile cash, lots, shares, costs, and P&L.
3. Reconcile holdings, sector, market-cap, and total portfolio weights.
4. Confirm every current price, benchmark, classification, and research link
   has a date and source.
5. Confirm every execution has an approved proposal and no proposal is executed
   twice.
6. Leave every unresolved limitation visible in DB-backed status, notes, or
   thesis records and in the user-facing response.

Intermediate JSON/JSONL/Markdown and calculation files are allowed. At
completion, Midas DB is the canonical persistence layer: save every accepted
portfolio change there, and do not substitute a spreadsheet, PDF, or other
filesystem artifact for the final DB state.

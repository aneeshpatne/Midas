---
name: rebalance
description: >
  Draft a manual rebalance proposal for a named paper portfolio. Use
  only after an explicit rebalance request, or when the user runs
  /rebalance.
metadata:
  short-description: "Manual paper-portfolio rebalance"
---
# Manual rebalance skill

Load `skills/paper-portfolio-core/SKILL.md` and
`skills/paper-portfolio-tools/SKILL.md` with this skill.

Use only after an explicit request to rebalance a named portfolio. There are no
calendar, drift, or background triggers.

1. Read the current DB-backed policy first, then transactions and derived state. Freeze the requested
   cut-off and refresh stale prices, corporate actions, benchmarks,
   classifications, costs, and thesis monitoring inputs.
2. Do not alter policy. Treat 60/25/15 invested-equity allocation, 0–20% cash,
   and the concentration levels as decision guidance. A warning is not a hard
   veto, but the proposal must explain why the exposure is justified.
3. Require current linked `Investable Now` research for every addition and
   material increase. Surface every `Weakened`, `Broken`, or `Needs Evidence`
   holding. Do not turn a thesis state into an automatic sale.
4. Create a whole-share `trade_proposal` with source-dated execution inputs,
   statutory charges, slippage, residual cash, and before/after holding,
   market-cap, sector, concentration, liquidity, thesis, expected-return, and
   benchmark-opportunity-cost views. Allow a valid no-trade conclusion.
5. Persist with `trade_proposal_create` and stop at `DRAFT`. Only explicit user
   approval naming the proposal ID authorizes a price freshness check,
   `trade_proposal_approve`, and atomic `trade_proposal_execute`. Do not use
   `transaction_create` for BUY or SELL. Recompute all DB-backed views after
   execution.

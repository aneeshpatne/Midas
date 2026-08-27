---
name: create
description: >
  Create a new named paper portfolio in Midas DB and stop at a draft
  trade proposal. Use when the user asks to create a paper portfolio or
  runs /create.
metadata:
  short-description: "Create a paper portfolio"
---
# Create portfolio skill

Load `skills/paper-portfolio-core/SKILL.md` and
`skills/paper-portfolio-tools/SKILL.md` with this skill.

Use when the user asks to create a new named paper portfolio.

1. Require a unique portfolio name and starting capital. Parse risk appetite,
   market-cap scope, sector/company scope, exclusions, and custom rules from the
   user's prompt. Store both the verbatim prompt and parsed mandate in policy.
   Use the default Moderate policy in `skills/paper-portfolio-core/SKILL.md` only for omitted fields.
   Freeze the creation cut-off and record every default used. A large-cap-only
   request becomes a 100%/0%/0% invested-equity target.
2. Create the portfolio with `portfolio_create`, create its account when
   applicable, and fund it with a `DEPOSIT` through `transaction_create`.
   Persist the full parsed policy in DB-backed portfolio fields or a dedicated
   policy record exposed by the midas-db-mcp. Intermediate working files are
   allowed, but creation is complete only after the DB writes succeed.
3. For researched initial holdings, run a fresh broad-universe equity skill
   over the requested market-cap/sector/company scope under the rolling
   five-year horizon. Ingest only focused companies with a
   validated `Investable Now` decision and store their exact research run ids and
   compact thesis snapshots. Preserve unallocated capital as cash.
4. Create one `trade_proposal` with whole-share quantities, price cut-off,
   statutory charges, slippage, residual cash, and before/after allocation,
   sector, concentration, liquidity, and thesis analytics. Explain every soft
   warning.
5. Persist it with `trade_proposal_create` and stop with the proposal in
   `DRAFT`. On explicit user approval naming its exact ID, refresh stale prices,
   call `trade_proposal_approve`, then atomically record its trades with
   `trade_proposal_execute`. Do not infer approval from the original creation
   request and do not use `transaction_create` for BUY or SELL.

---
name: performance-refresh
description: >
  Refresh prices, analytics, or efficacy for a named paper portfolio
  without proposing trades. Use when the user asks to refresh portfolio
  performance or runs /performance-refresh.
metadata:
  short-description: "Refresh portfolio analytics"
---
# Performance-refresh skill

Load `skills/paper-portfolio-core/SKILL.md` and
`skills/paper-portfolio-tools/SKILL.md` with this skill.

Use only when the user asks to refresh prices, analytics, or efficacy.

1. Read the named portfolio and freeze the requested cut-off. Retrieve current
   holding prices, relevant dividends/corporate actions, classification
   vintages, and like-for-like TRI benchmark observations.
2. Record corporate actions and dividends as DB transactions before upserting
   the market prices they affect. Preserve failed retrievals as DB-backed gaps.
3. Read the DB ledger and calculate current value, cash, invested capital,
   realized/unrealized P&L, money-weighted XIRR, time-weighted return, relative
   TRI return, drawdown, market-cap allocation, sector exposure, and warnings.
4. Persist refreshed prices and accepted portfolio data in DB, then return the
   derived view. Intermediate files are allowed. Do not propose or execute
   trades unless the user separately asks for a rebalance.

---
name: capital-change
description: >
  Record a contribution or withdrawal on an existing named paper
  portfolio. Use when the user adds or withdraws capital or runs
  /capital-change.
metadata:
  short-description: "Portfolio deposit or withdrawal"
---
# Capital-change skill

Load `skills/paper-portfolio-core/SKILL.md` and
`skills/paper-portfolio-tools/SKILL.md` with this skill.

Use for contributions or withdrawals to an existing named portfolio.

1. Read the exact portfolio metadata/policy and transactions from Midas DB,
   then derive current state. Require amount and
   effective date; default the effective date to the user's stated date or the
   current date, never to a market date inferred from prices.
2. Record a `DEPOSIT` or `WITHDRAWAL` transaction. Reject a withdrawal that would
   create negative cash; propose required sales instead.
3. For a contribution, refresh material stale inputs and create a policy-
   compliant deployment proposal using currently qualified holdings and fresh
   research for any new company. Show whole-share trades, costs, residual cash,
   before/after analytics, and all soft warnings.
4. The contribution is accepted cash, but proposed trades remain `Draft` until
   their exact proposal ID is approved. Recompute the DB-backed view after
   each accepted transaction. A file export is optional working output, never
   the canonical accepted state.

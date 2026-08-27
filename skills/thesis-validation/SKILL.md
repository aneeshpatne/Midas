---
name: thesis-validation
description: >
  Re-validate one or more holding theses with fresh isolated
  single-stock research. Use when the user asks to validate theses or
  runs /thesis-validation.
metadata:
  short-description: "Re-validate holding theses"
---
# Thesis-validation skill

Load `skills/paper-portfolio-core/SKILL.md` and
`skills/paper-portfolio-tools/SKILL.md` with this skill.

Use when the user asks to validate one or more holding theses at a future date.

1. Read the named portfolio's compact stored thesis snapshots and freeze the
   requested validation cut-off. Do not open the prior research runs during the
   fresh research pass.
2. Run one new isolated single-stock research skill per selected holding
   using the rolling five-year horizon. Each run re-retrieves current evidence
   and produces its own validated conclusion without portfolio or prior-run
   context.
3. In the portfolio layer, compare each fresh conclusion with the stored thesis,
   controlling assumptions, valuation condition, and invalidation triggers.
   Assign exactly `Intact`, `Weakened`, `Broken`, or `Needs Evidence` and state
   the decisive change and portfolio implication.
4. Append one DB thesis revision per holding with both thesis versions, the
   exact new research run id, cut-offs, status, evidence gap, controlling
   change, and next review condition. Link the run with
   `research_link_portfolio`, then recompute the DB-backed views.
5. Never trade or silently open a rebalance. If action may be warranted, show
   the named thesis status and invite a separate manual rebalance request.

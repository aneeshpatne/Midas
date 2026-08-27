---
name: valuation-auditor
description: >
  Blind independent replication of focused equity valuation, return, and
  sensitivity analysis. Load only for the bounded valuation-auditor worker
  pass in an active Midas research run; do not use it for final decisions.
---
# Valuation-auditor pass

Independently reconstruct the focused-set valuation and return ranges without
seeing or reverse-engineering the primary analyst's model. This is a
replication control, not a request for a target price or final stance.

Read `skills/equity-research-core/SKILL.md`,
`skills/equity-research-tools/SKILL.md`, this skill, the active mandate, and
only the authorized current-run `source`, `retrieval`, `company`, `metric`,
and `claim` records. Do not receive or inspect primary `model`, evidence-audit
conclusions, `decision`, `skeptic`, report-draft, or unrelated-run records.

Use only exposed Midas MCPs and native web search/open/find/web-accessible PDF
inspection for any necessary evidence closure. Never use model memory, browser
state, connectors, filesystem data, shell networking, consensus targets, or ad
hoc APIs as evidence.

## Independent replication

For every assigned focused company:

1. Reconcile current price/date, corporate actions, diluted share basis,
   financial basis, net debt or surplus cash, minority interests, exceptional
   items, and dividends. Reject mixed units or periods before calculating.
2. Rebuild a normalized starting earning-power or cash-flow measure from the
   authorized records. For banks, insurers, cyclicals, holding companies, and
   other distinct economics, use the applicable sector convention rather than
   forcing generic FCF.
3. Use two economically distinct, sector-appropriate lenses. Include a
   market-implied expectations or reverse-valuation test when it has more
   diagnostic value than a second intrinsic-value model.
4. Construct bear/base/bull paths over the exact mandate horizon. State the
   causal operating assumptions, terminal economics, reinvestment needs,
   dilution, dividends, and balance-sheet path; do not extrapolate historical
   growth or management guidance mechanically.
5. Calculate annualized nominal total returns and compare them with the same
   relevant TRI and risk-premium convention. Do not probability-weight
   scenarios unless defensible probabilities and their basis are explicitly
   retrieved and recorded.
6. Identify the highest-impact assumption, the rounded breakpoint at which the
   economic conclusion changes, and severe-but-plausible downside. Test at
   least the two most decision-sensitive inputs jointly when they interact.
7. Verify formulas dimensionally and by an independent recomputation. Trace
   every external input to source IDs and label every transformation,
   normalization, estimate, and inference.

## Handoff

Return proposed `audit` records with `audit_role: valuation-auditor`, company,
methods, formulas, normalized inputs, scenarios, outputs, benchmark/hurdle,
source IDs, sensitivities, breakpoints, and confidence. Also state:

- missing or weak inputs and the reasonable favorable/adverse bounds used;
- any method disagreement and its economic cause;
- the independently supported value/return zone without assigning a stance;
  and
- metadata and extracts for any new authorized sources.

The primary compares this blind result with its own `model` records, resolves
material differences in a lead `audit` resolution, and owns all DB writes and
investment decisions.

---
name: skeptic
description: >
  Isolated skeptic pass that challenges primary equity research without
  making the final decision. Load only for the skeptic worker pass. Use
  when running /skeptic.
metadata:
  short-description: "Isolated research challenge pass"
user-invocable: false
---
# Isolated skeptic pass

Challenge the primary research without making the final decision. Use
`skills/equity-research-core/SKILL.md`, `skills/equity-research-tools/SKILL.md`, the active run's DB-backed mandate, and only the
authorized evidence records listed in the assignment.

This isolated pass is a required control against confirmation bias and false
negatives whenever the harness can provide the runtime and isolation required
by the root router. It is not a substitute for the primary's initial sweep or
an authority to eliminate, restore, rank, persist, or decide a company.

Do not read the primary analyst's stance, report draft, decision records, or
unrelated companies. Do not inspect any other research run. The assignment
should include question, hypothesis, source, company, metric, claim, screen,
primary model, and verified evidence/valuation-audit records for each focused
company and every broad-universe exclusion packet. Include `Watch` records
whose unresolved question could materially change the ranking.

For each assigned company test:

- the strongest reason the business may be less durable than claimed;
- normalized earnings, cash conversion, accounting, dilution, and the weakest
  model input;
- governance, capital allocation, solvency, liquidity, regulation, and
  permanent-impairment paths;
- whether the base case embeds optimistic growth, margin, ROE, credit-cost, or
  terminal-value assumptions;
- the severe but plausible bear path and its annualized return;
- whether the evidence auditor's contradiction search and the blind valuation
  replication expose unresolved primary-case dependence or anchoring;
- the strongest direct or index alternative;
- whether the conclusion applies the user's declared risk appetite rather than
  silently imposing a more conservative one; and
- evidence that would invalidate the objection.

For every broad-universe exclusion, test whether the minimum packet is complete
or explicitly bounded; the structured-baseline, business-deepening, and
common-basis comparison passes were completed; the controlling evidence is
cited and current; original sources were inspected for the controlling and
strongest positive or contrary cases; and missing data, shallow MCP coverage,
a generic assumption, early batch order, a proxy threshold, context pressure,
or a workload ceiling caused a false negative. Use only the exposed research
MCPs and targeted native web-search/open/find/PDF research under `skills/equity-research-tools/SKILL.md` when
new evidence directly resolves a material challenge. Recommend restoration
only when a named, obtainable fact or supported economic argument could
materially change the funnel decision.

Return compact `skeptic` records with objection, severity (`Critical`,
`Material`, or `Minor`), source IDs, unresolved issue, and the plausible effect
on the stance. Distinguish falsified, weakened, unresolved, and survived
hypotheses. Retrieve new evidence only when it directly resolves a material
challenge; return source metadata for the primary to merge into the ledger.
Return records to the primary for DB append. Intermediate working files are
allowed, but they are not the final skeptic output; do not write directly to
another run.

If an isolated Luna/xhigh worker is genuinely unavailable, the primary performs
the same bounded pass linearly, labels it `self-skeptic`, and records the exact
capability limitation. Do not silently omit the pass merely because spawning is
inconvenient or slower.

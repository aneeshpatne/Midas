---
name: broad-universe
description: >
  Screen six or more names, an index, sector, or open universe with a
  primary-owned sweep and evidence-backed funnel. Use when the user asks
  for a universe, index, or sector screen, or runs /broad-universe.
metadata:
  short-description: "Index, sector, or open-universe screen"
---
# Broad-universe skill

Load `skills/equity-research-core/SKILL.md` and
`skills/equity-research-tools/SKILL.md` with this skill.

Use for six or more named companies, an index, sector, screen, or open-ended
universe. The objective is a thorough, primary-owned initial research sweep,
followed by an evidence-backed funnel and comparable focused research. A broad
run may use bounded depth before focused work, but it must not eliminate a
company through assumptions, missing data, or an automatic proxy cutoff.

## 1. Mandate and universe

Resolve the universe source, as-of date, inclusion rules, exact user-defined
horizon, and explicit risk appetite or loss tolerance. Freeze the cut-off and
the risk-appetite translation required by `skills/equity-research-core/SKILL.md` in
`research_runs.mandate_md`. Record known factor or methodology bias. Reconcile
every constituent identity before using its data; index weight is not
investment merit.

Register the universe-level decision question, falsifiable advancement and
exclusion hypotheses, strongest alternative explanations, common materiality
rules, and the observations that would reverse a provisional disposition.
Company-specific hypotheses may be appended during the sweep, but do not
rewrite them after disposition evidence is known.

There is no fixed focused-research ceiling. Work through large universes in
batches and advance every company whose researched case remains plausibly
competitive. Batch size is an execution detail, not an exclusion quota.

## 2. Primary initial research sweep

The primary, not a semantic research worker or subagent, gives every
constituent a substantive sector-aware initial research packet through the
three ordered passes below. The first pass builds the common structured
baseline, the second deepens the qualitative case and closes gaps, and only the
third may assign a funnel disposition. Do not eliminate companies while
retrieval is still in progress or let an early negative signal reduce the
remaining packet.

Use only the exposed Midas MCPs and the harness's native web-search,
page-open, text-find, and web-accessible PDF inspection tools for evidence.
Start with applicable Midas MCPs, then use the native web tools to close every
material fact that Midas does not provide, covers only thinly, reports stale,
or conflicts on. Open and inspect original sources; snippets, model memory,
browser state, filesystem data, other retrieval routes, and MCP omissions are
not evidence.

### 2.1 Structured baseline — no dispositions

Reconcile every constituent on a sector-appropriate common basis before
forming the shortlist. For every company capture:

- legal identity, reporting basis, segments, material subsidiaries, corporate
  actions, share-count basis, and the actual revenue and profit model;
- preferably five or more years of sector-appropriate operating economics,
  per-share growth, earnings quality or cash conversion, returns on capital or
  equity, leverage or funding resilience, and dilution, using shorter history
  only when clearly labeled and not extrapolated;
- current price, liquidity plausibility, and simple sector-appropriate
  valuation context, without turning a multiple into a decision; and
- the returned dates, definitions, source URLs, MCP omissions, stale fields,
  and conflicts that require targeted web closure.

Do not assign `Advance`, `Watch`, or `Exclude from focused research` in this
pass. A negative screen value creates a research question; it does not shorten
the next pass.

### 2.2 Business deepening and gap closure — no dispositions

For every constituent, use targeted native-web research to resolve material
MCP gaps and build a balanced qualitative case. The packet must cover:

- business economics and competitive position: customers, products, demand
  drivers, pricing power, concentration, capital intensity, cyclicality,
  regulation, and the evidence for or against durability;
- reinvestment and capital allocation: runway, incremental economics where
  knowable, capex, acquisitions or divestitures, debt and equity issuance,
  distributions, and management delivery versus prior claims;
- balance-sheet resilience and the sector-specific failure path;
- current governance, ownership, auditor, regulatory, related-party,
  contingent-liability, dilution, and capital-allocation evidence where
  material;
- preliminary valuation and opportunity-cost plausibility under reasonable
  favorable and adverse interpretations for the declared horizon and risk
  appetite; and
- the strongest supported positive case, strongest supported negative case,
  the fact most likely to change either case, and every remaining gap.

For any proposed exclusion, inspect original-source evidence for both the
controlling reason and the strongest reasonable positive or contrary case.
Confirm that an apparently fatal issue is current, applies to the reconciled
entity, and is material; a fatal issue may stop elaborate modeling only after
that verification and the rest of this bounded packet are recorded. When an
original source cannot be reached through the authorized tools, classify the
gap instead of treating the inaccessible claim as fact.

Do not assign a funnel disposition in this pass. Record completion and gaps so
the later comparison cannot silently treat shallow coverage as negative
evidence.

### 2.3 Common-basis comparison and disposition gate

After every constituent has completed or explicitly bounded both earlier
passes, compare the packets on a common sector-aware basis and assign funnel
dispositions. For a very large universe, work in batches, but keep batch-level
dispositions provisional until all batches have received both passes and the
primary has calibrated cross-batch opportunity cost and false-negative risk.
Batch order, context limits, and workload may not decide an exclusion.

All dispositions remain provisional until the evidence, valuation where
applicable, and skeptic controls finish and the primary resolves restoration
findings. The primary still authors the disposition before and after review;
workers only challenge it.

Each company's `screen` record must contain:

- completion status for the structured-baseline, business-deepening, and
  common-basis comparison passes;
- all baseline and qualitative packet fields above, including valuation and
  liquidity plausibility against the declared horizon, risk appetite, and
  relevant opportunity cost;
- the strongest supported positive case and strongest supported negative case;
- MCP coverage, targeted-web retrieval and source IDs, conflicts, and remaining
  gaps; and
- packet status, funnel disposition, exclusion-gate result, controlling
  evidence, strongest contrary case, and the primary's concise rationale.

Packet status is `Complete`, `Material gaps bounded`, or `Decision-critical
gap`. A bounded packet may support a disposition only when reasonable favorable
and adverse interpretations leave it stable. A decision-critical gap cannot
support exclusion.

Assign only provisional:

- `Advance` — a plausible positive, contrarian, or opportunity-cost case
  deserves focused work;
- `Watch` — an unresolved fact or changing condition retains meaningful
  decision value; or
- `Exclude from focused research` — cited economics, valuation, risk, or
  opportunity-cost evidence makes deeper work lower value after testing the
  strongest reasonable contrary case.

An exclusion requires completed or explicitly bounded baseline and deepening
passes, common-basis comparison, primary-authored controlling evidence and
source IDs, original-source inspection for the controlling and contrary cases,
the material gaps, and an explanation of why reasonable favorable
interpretations do not justify advancement. If any gate is absent, use
`Advance` or `Watch`; do not exclude. Never exclude from a missing field, thin
MCP response, generic sector belief, index weight, assumed business quality,
one ratio, mechanical score, early batch order, context pressure, or fixed
capacity limit. Exclusion is a funnel disposition, not a final `Avoid` stance.

No number of passed signals automatically advances or excludes a company.
Rank expected decision value using researched business potential, valuation
plausibility, severity and resolvability of uncertainty, false-negative cost,
and usefulness as an alternative. Advance every plausibly competitive company;
use alphabetical symbol only as the final tie-breaker for presentation.

PTC may perform only deterministic Midas normalization, coverage joins,
deduplication, and screen arithmetic. Adaptive web retrieval, packet
interpretation, ranking, advancement, and exclusion remain direct primary
work. Use the structured `ptc` result and documented direct-call fallback when
available and needed.

## 3. Focused research

Apply the full core sequence on a comparable basis to every `Advance` company
and every later restoration. Complete the applicable high-value web-enrichment
matrix in `skills/equity-research-tools/SKILL.md`. A verified fatal issue may stop later modeling only after
the controlling evidence and contrary case are recorded. Otherwise complete
normalized economics, two appropriate valuation lenses, bear/base/bull
returns, TRI opportunity cost, governance review, liquidity, mandate fit, and
thesis invalidation tests.

Do not assign final investment stances to sweep-only companies. Preserve their
packet status, funnel disposition, controlling evidence, gaps, and concise
reason in the ledger and report.

## 4. Independent controls, restoration, and decisions

Run one evidence-auditor pass across every completed packet after the
provisional funnel and focused work. It tests source lineage, temporal
integrity, search symmetry, forensic coverage, unsupported claims, and every
provisional exclusion. Use the fewest practical disjoint sector batches only
when the full authorized payload does not fit; worker output never substitutes
for the primary's common-basis comparison.

Run one valuation-auditor pass across all focused companies, blind to primary
models and decisions. It independently reconstructs sector-appropriate value,
return, downside, opportunity cost, sensitivities, and breakpoints on a common
basis after the primary verifies evidence-audit sources and closes or bounds
material input gaps. The primary verifies all proposed `audit` records and
resolves material evidence and model differences.

Then run the isolated skeptic with authorized pre-decision evidence, primary
models, and verified audit findings for every focused company and every
provisional exclusion packet; include `Watch` records when their unresolved
issue could change the ranking. It challenges positive cases and audits
exclusions for unsupported assumptions, missing-data penalties, proxy bias,
shallow web closure, model anchoring, and ignored contrary evidence. It does
not make the final funnel or investment decision.

Any independent control may recommend restoration only when a named obtainable
fact, source defect, model difference, or supported economic argument could
materially change an exclusion. The primary resolves the finding, performs full
focused research on each restored company, applies the same evidence,
valuation, and skeptic checks to the incremental case, and records the result.
There is no restoration or focused-set cap. Do not spawn a new worker per
restored company; use one bounded follow-up to an existing role when the
harness supports it, otherwise perform and disclose the incremental self-audit.

If a compatible isolated worker is genuinely unavailable, perform its bounded
pass as `self-evidence-audit`, `self-valuation-audit`, or `self-skeptic` and
disclose the exact limitation in the mandate and report. Merge all controls,
resolve material objections, finalize funnel dispositions, assign final
decisions only to focused companies, append dated monitoring forecasts, and
run every publication check.

## 5. Report

The report persisted in `research_runs.report_md` must include:

- total universe size, packet-status and three-pass completion counts, MCP
  coverage, and targeted-web gap-closure coverage;
- counts for `Advance`, `Watch`, `Exclude from focused research`, focused
  research, evidence audit, blind valuation audit, skeptic review,
  restorations, and each final stance;
- one compact row per constituent with packet status, final funnel disposition,
  controlling cited reason, material gap, independent-control outcome, and
  skeptic outcome;
- full decision cases only for focused companies, including declared
  risk-appetite fit;
- the best-supported candidate among the focused set, explicitly scoped as
  such; and
- zero `Investable Now` as a valid result, accompanied by the closest focused
  candidate and its controlling price or evidence condition.

Do not call a funnel exclusion `Avoid`, claim that sweep-only companies received
focused depth, or claim to have found the best company in the full universe
unless every constituent received equivalent focused research.

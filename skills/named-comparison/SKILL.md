---
name: named-comparison
description: >
  Compare two to five explicitly named listed companies at focused depth.
  Use when the user names 2-5 companies to compare or runs
  /named-comparison.
metadata:
  short-description: "Two-to-five company comparison"
---
# Named-comparison skill

Load `skills/equity-research-core/SKILL.md` and
`skills/equity-research-tools/SKILL.md` with this skill.

Use for two to five explicitly named listed companies. Research every name at
focused depth; do not screen a named company out before comparison.

1. Resolve every legal identity, the exact user-defined horizon, and the
   explicit risk appetite or loss tolerance. Freeze one cut-off, financial
   basis, benchmark convention, appetite translation, risk-premium method, and
   scenario convention in `research_runs.mandate_md`. Register the common
   decision question plus company-specific hypotheses, strongest alternatives,
   falsifiers, thresholds, and materiality before substantive retrieval.
2. In the active run's `research_evidence` rows, reconcile fiscal periods,
   corporate actions, share
   counts, sector economics, and data coverage before comparing results.
   PTC may perform only deterministic joins, deduplication, and arithmetic
   after tool schemas and eligible callers are verified; company judgment and
   source selection remain direct.
3. Apply the full core analysis to every name. A verified fatal issue may stop
   unnecessary valuation work, but its evidence and controlling reason remain
   directly comparable.
   After each Midas baseline, complete comparable high-value web enrichment for
   every named company so ranking differences do not reflect unequal source
   depth. Record inapplicable and unresolved areas explicitly.
4. For every otherwise plausible company, use two sector-appropriate valuation
   lenses, bear/base/bull returns, and the same opportunity-cost convention.
   Apply the user's appetite consistently to mandate fit without altering the
   objective business rating or overlooking permanent-loss evidence.
5. Run one isolated evidence-auditor pass across the comparison. After the
   primary verifies its new sources and closes or bounds material input gaps,
   run one valuation-auditor pass blind to primary models, audit conclusions,
   and decisions. Use the fewest practical disjoint batches only if needed and
   compare coverage and methods on a common basis so worker depth cannot create
   ranking bias. The primary verifies proposed `audit` records and resolves
   material differences.
6. Run the isolated skeptic on every named company with primary models and
   verified audit findings but without decision or report records. Merge
   objections and evidence, resolve disagreements, then assign ratings,
   stances, confidence, and a complete ranking.
7. Append comparable dated monitoring forecasts for every name. Validate and
   persist one comparative report in `research_runs.report_md`.
   Explain the controlling
   difference between adjacent ranks and identify the best-supported company,
   while allowing zero `Investable Now` conclusions.

Every named company appears once in the decision table and receives a current
stance. Do not use broad-universe screening dispositions or imply that a lower
rank is an `Avoid` unless its own evidence supports that stance. Explain the
material primary-versus-independent evidence and valuation differences so the
ranking is reproducible rather than merely ordinal.

---
name: single-stock
description: >
  Research exactly one listed company as an isolated Midas equity-research
  run. Use when the user names one company or stock, asks for a single-stock
  IC memo, or runs /single-stock.
metadata:
  short-description: "One-company equity research"
---
# Single-stock skill

Load `skills/equity-research-core/SKILL.md` and
`skills/equity-research-tools/SKILL.md` with this skill.

Use for exactly one listed company. Peers and indices are comparators, not an
expanded research universe.

1. Resolve the company's legal identity, exact user-defined horizon, and
   explicit risk appetite or loss tolerance. Create the run with
   `research_run_create` and persist the frozen mandate and risk translation in
   `research_runs.mandate_md`. Before substantive retrieval, append the
   registered decision question, primary hypothesis, strongest alternative,
   falsifiers, decision thresholds, and materiality convention.
2. Append `research_evidence` rows through the complete analysis sequence in
   `skills/equity-research-core/SKILL.md`. Focus retrieval on claims capable of changing business quality,
   valuation, downside, or stance.
   PTC is optional for deterministic normalization or model arithmetic only;
   keep all source selection, interpretation, skepticism, and final validation
   direct.
   After the Midas baseline, complete the high-value web-enrichment matrix in
   `skills/equity-research-tools/SKILL.md`; record each material retrieval or unresolved limitation.
3. Complete two sector-appropriate valuation lenses and bear/base/bull returns
   unless a verified earlier fatal issue supports `Avoid`. Compare the company
   with its most relevant direct alternative and diversified TRI, and apply the
   declared appetite to mandate fit without changing objective business
   quality or excusing permanent-loss evidence.
4. Run the isolated evidence auditor on the source, retrieval, metric, and
   claim graph. The primary verifies its proposed sources and closes or bounds
   material gaps, then runs the valuation auditor blind to primary models,
   audit conclusions, and decisions. Append verified proposed `audit` records
   and resolve material evidence or model differences.
5. Run the isolated skeptic on the complete pre-decision evidence, primary
   models, and verified audit findings, excluding decision and report records.
   Merge its evidence and objections, then record lead resolutions and the
   final decision.
6. Append dated, measurable monitoring forecasts. Run all publication checks,
   persist the focused IC memo in
   `research_runs.report_md`, and complete the run through midas-db-mcp.

The report must state one business rating, one investment stance, confidence,
the current valuation zone or evidence condition, the permanent-loss path, the
highest-impact model assumption, mandate fit under the declared risk appetite,
what would invalidate the thesis, the material independent-audit differences,
and the measurable outcomes that will test the thesis.

---
name: evidence-auditor
description: >
  Isolated equity-research evidence, provenance, contradiction, and forensic
  coverage audit. Load only for the bounded evidence-auditor worker pass in an
  active Midas research run; do not use it for final investment decisions.
---
# Evidence-auditor pass

Audit whether the primary case is supported by timely, independent, correctly
interpreted evidence. Do not rank, exclude, assign a business rating or stance,
write to Midas DB, or draft the report.

Read `skills/equity-research-core/SKILL.md`,
`skills/equity-research-tools/SKILL.md`, this skill, the active mandate, and
only the active-run records authorized in the assignment. Do not inspect
another run or use a primary decision, report draft, or later-stage record.

## Inputs and isolation

Receive the run's `question`, `hypothesis`, `source`, `retrieval`, `company`,
`metric`, `claim`, and applicable `screen` records. For broad universes, audit
the run-wide packet or the assigned disjoint batch after the primary sweep and
provisional funnel but before dispositions are finalized. Treat the primary's
provisional disposition as a proposition to test, not a decision to defend.
Treat management claims, secondary summaries, and provider-derived metrics as
propositions to verify, not as independent corroboration.

Retrieve new evidence only through exposed Midas MCPs or native web
search/open/find/web-accessible PDF inspection. Use Midas for structured
baseline checks and native web tools for original-source verification. Do not
use model memory, browser state, connectors, filesystem data, shell networking,
or ad hoc APIs as evidence.

## Audit procedure

1. Reconcile entity, symbol, reporting basis, units, periods, share count,
   corporate actions, price timestamp, and cut-off compliance. Flag look-ahead
   evidence and mixed standalone/consolidated or fiscal/calendar bases.
2. Build a claim-source graph for every decision-critical or material claim.
   Distinguish the originating source from copies of it; multiple reproductions
   of one issuer statement are one evidence lineage, not triangulation.
3. Grade each claim on authority, directness, independence, freshness,
   measurement quality, and consistency. A single authoritative primary record
   may establish a filed fact; causal, durability, and forward claims normally
   require independent evidence or explicit uncertainty.
4. Test search symmetry. For each material positive claim search for the
   strongest plausible contradiction; for each adverse or exclusion-driving
   claim search for the strongest plausible benign explanation or contrary
   evidence. Absence from a search result is not evidence of absence.
5. Audit accounting and forensic coverage where applicable: exceptional-item
   normalization, cash-flow classification, capitalized costs, working-capital
   reversals, receivable/inventory quality, related parties, contingent
   liabilities, auditor or key-officer changes, dilution, pledges, covenants,
   subsidiary leakage, and management promises versus outcomes.
6. Check that comparison claims use genuinely comparable definitions and that
   base-rate or peer evidence matches sector, size, cycle, and period. Flag
   survivor bias, cherry-picked windows, and unrepresentative peers.
7. Stop when each issue is resolved, bounded under favorable and adverse
   interpretations, or exhausted under the core evidence-gap rule.

## Handoff

Return compact proposed `audit` records with:

- `audit_role: evidence-auditor`, scope or company, audited claim ID, finding,
  severity (`Critical`, `Material`, or `Minor`), and check type;
- supporting and contradicting source IDs, source-lineage assessment, cut-off
  status, and confidence;
- the exact correction or retrieval needed, whether it is decision-critical,
  and the plausible effect if unresolved; and
- metadata and decision-used extracts for any new Midas or web sources so the
  primary can verify and append them.

Also return a coverage summary: claims tested, unsupported material claims,
conflicts, look-ahead failures, asymmetric searches, unresolved forensic gaps,
and pass/batch scope. The primary owns every correction, DB append, funnel
judgment, and final decision.

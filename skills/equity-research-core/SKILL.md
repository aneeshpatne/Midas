---
name: equity-research-core
description: >
  Shared Indian listed-equity research standard: mandate, DAG, ratings,
  valuation, evidence ledger, report, and publication checks. Load with
  every equity-research run. Not a standalone action.
metadata:
  short-description: "Shared equity-research standard"
user-invocable: false
disable-model-invocation: true
---
# Core equity-research standard

Act as a skeptical, long-horizon Indian public-equity analyst. Seek durable
per-share compounding at an attractive risk-adjusted return over the user's
specified horizon. Think like an owner. Do not let price momentum, recent
results, broker targets, flows, social popularity, index membership, a low
multiple, or a high dividend yield increase business quality.

Strictness applies to provenance, arithmetic, comparability, and intellectual
honesty. It does not mean converting unavailable data into failure or rejecting
every company that lacks ideal diligence coverage. Apply skepticism
symmetrically: test both the attractive thesis and the exclusion case, and do
not make caution itself a source of investment merit.

## Mandate defaults

The research run `mandate_md` records:

- run ID, workflow, company/universe, user-defined horizon, and frozen cut-off;
- the pre-registered decision question, primary hypothesis, strongest competing
  hypothesis, observable falsifiers, decision thresholds, and materiality
  convention; do not rewrite them after seeing results—append amendments with
  time and reason;
- the user's risk appetite or loss-tolerance wording and its explicit
  translation into hurdle, downside tolerance, liquidity expectations, and
  mandate-fit criteria;
- actual primary runtime, execution mode, and callable research tools;
- whether native web search, page opening, text finding, and web-accessible PDF
  inspection are available, plus the MCP/web-only evidence boundary and
  authorized enrichment scope;
- whether Programmatic Tool Calling (PTC) is exposed, which tools are eligible,
  which bounded nodes may use it, and the direct-call fallback;
- required independent controls, worker runtime, isolation mode, role/batch
  map, authorized records, blinding rules, and any exact self-audit fallback;
- consolidated financial basis unless a different basis is necessary;
- relevant sector/size TRI and broad-market TRI; never compare dividend-
  inclusive company returns with a price-only index;
- user hurdle when supplied; otherwise a forward TRI return range plus a
  clearly justified company-risk premium calibrated to the declared appetite
  and evidenced permanent-loss risk—not automatically widened for volatility,
  cyclicality, or drawdown the user has said they can tolerate;
- user position size when supplied; otherwise an INR 10 lakh liquidity
  notional with a 10% median-daily-value participation assumption;
- requested exclusions, constraints, and every default actually used.

Use one exact primary horizon. Optional checkpoints cannot replace or blend it.
Freeze current prices, filings, market inputs, and benchmark evidence at the
cut-off; later-published evidence is outside the run.

Preserve objective business quality, evidence confidence, and mandate fit as
separate judgments. A more aggressive appetite can accept greater price
volatility, cyclicality, concentration, or range width; it cannot convert
fraud, insolvency, destructive dilution, or verified governance abuse into
sound quality. Uncertainty widens ranges or lowers confidence and becomes a
veto only when the evidence-gap rule makes the conclusion indefensible.

## Scientific research protocol

Treat the run as a falsifiable decision study, not a persuasive narrative.
Before substantive company evidence is gathered, record `question` and
`hypothesis` rows for the primary proposition and strongest live alternative.
For each hypothesis specify the observation that would support it, the
observation that would weaken or falsify it, the horizon over which it applies,
and the decision it could change. Do not force a numeric prior without an
authorized, comparable base rate.

Apply these controls throughout the run:

1. **Separate observation from interpretation.** Label filed facts,
   management claims, third-party estimates, calculations, and analyst
   inferences. A conclusion cannot be its own evidence.
2. **Use symmetric tests.** Seek the strongest plausible disconfirming evidence
   for positive claims and the strongest plausible benign explanation or
   contrary evidence for adverse claims. Record the search even when it fails;
   failed discovery is not evidence of absence.
3. **Track evidence lineage.** Multiple sites copying one filing or statement
   are one lineage. Use independent corroboration for material causal,
   durability, and forward claims when obtainable. One authoritative primary
   source may be sufficient for a directly filed fact.
4. **Preserve temporal integrity.** Use only information published by the
   frozen cut-off, distinguish event date from publication date, and prevent
   later outcomes from leaking into historical judgments.
5. **Use comparable base rates.** When base-rate evidence is decision-relevant,
   retrieve it for an appropriate sector, size, cycle, and period. Explain
   mismatches and never substitute model memory or an arbitrary peer set.
6. **Make uncertainty operational.** Express it as bounded assumptions,
   scenario ranges, confidence, named evidence gaps, and breakpoints. Do not
   hide it in vague prose or manufacture precision with unsupported scenario
   probabilities.
7. **Prefer replication over consensus.** Independently recompute material
   derived metrics and valuation results. Resolve differences economically;
   neither the primary nor the auditor wins by default.
8. **Leave testable forecasts.** For each focused company record a small set of
   dated, measurable operating or balance-sheet expectations, the expected
   range, source basis, and thesis implication. These are monitoring forecasts,
   not facts available at the cut-off.

Use decision relevance and expected information value to allocate research
effort. Stop a retrieval branch when the claim is resolved, bounded favorable
and adverse cases cannot change the action, or authorized high-authority routes
are exhausted and the gap is classified. Do not stop because a preferred
narrative already has enough supporting citations.

## Canonical run DAG

Use this dependency graph as the control flow for every run. It is a prompt
guardrail, not an additional stage or artifact.

```mermaid
flowchart TD
    M[ M: mandate and cut-off ] --> E[ E: identity and baseline evidence ]
    E -->|single stock| F1[ F: focused company case ]
    E -->|named comparison| F2[ F: common-basis company cases ]
    E -->|broad universe| S[ S: primary all-company research sweep ]
    S --> U[ U: provisional evidence-backed funnel ]
    U --> F3[ F: all advanced company cases ]
    F1 --> A[ A: evidence and forensic audit ]
    F2 --> A
    F3 --> A
    A --> L[ L: blind valuation replication ]
    L --> K
    K -->|broad material false negative| X[ X: restored-company focused research ]
    K --> D[ D: lead resolution and decisions ]
    X --> D
    D --> V[ V: arithmetic and publication validation ]
    V --> R[ R: final IC report ]
```

Node contract:

- `M` freezes identity, horizon, cut-off, basis, benchmarks, defaults, tools,
  and execution mode in the run's `mandate_md`.
- `E` writes identity, source, metric, and coverage records to the run's
  `research_evidence` ledger. PTC may be used here only for deterministic
  retrieval normalization, joins, deduplication, and screen arithmetic.
- `S` is performed by the primary as three ordered passes: structured baseline,
  qualitative enrichment and gap closure, then common-basis comparison. It
  gives every broad-universe constituent a sector-aware minimum research
  packet, closes material MCP gaps with targeted harness web research, and
  writes complete `screen` records. No disposition is assigned during the
  first two passes. Semantic sweep research and exclusion judgments must not
  be delegated.
- `F` closes high-value Midas gaps through direct harness web research, then
  writes decision-used claims and models. It may read its upstream `M`, `E`,
  `S`, and `U` records as applicable, never another run or a later decision.
- `U` assigns primary-authored, evidence-backed provisional funnel dispositions
  and advances every plausibly competitive company without a fixed shortlist
  cap. Exclusions are not final until independent controls and restoration
  review finish. It never assigns a final investment stance.
- `A` is the isolated evidence-auditor pass. It checks claim-source lineage,
  temporal integrity, contradictions, search symmetry, accounting and
  governance coverage, and every broad exclusion packet. It returns proposed
  `audit` records and does not decide. The primary verifies its new sources and
  closes or bounds material gaps before authorizing `L` inputs.
- `L` is the blind valuation-auditor pass. It receives source, metric, claim,
  and mandate records but no primary model outputs, evidence-audit conclusions,
  or decisions; it independently reconstructs valuation, returns, sensitivity,
  and arithmetic in proposed `audit` records.
- `K` reads only the authorized pre-decision evidence and writes `skeptic`
  records. It may read primary models plus verified `A` and `L` handoffs, but
  not primary `decision` records or a report draft. For a broad universe it
  challenges every focused case and every exclusion packet; it must not make
  the final funnel decision.
- `X` is optional focused research for each exclusion the primary restores
  after a material skeptic false-negative finding; it is not an abbreviated
  final decision or an unbounded loop.
- `D` merges evidence, independent audits, and objections; resolves or
  preserves material differences; finalizes broad dispositions; and writes
  `decision` records.
- `V` writes `validation` records and blocks publication on unresolved
  decision-driving conflicts. Deterministic arithmetic may use PTC, but final
  citation and original-source validation remains direct.
- `R` reads the validated ledger and writes the run's `report_md`.

An arrow is a hard read-after-write dependency. Do not ask a worker to read a
downstream node, overlap workers that may call Midas, or create a separate
artifact for a node. If spawning is unavailable, execute the same controls
linearly under their named `self-*` modes and record the exact limitation in
`M`.

## Analysis sequence

For a company, answer these questions in order. In a broad-universe run, steps
1–5 and a preliminary sector-appropriate valuation and opportunity-cost check
must be completed or explicitly bounded before any funnel exclusion. A
confirmed fatal issue may stop elaborate modeling, but not verification of its
current status, scope, materiality, actual business context, and strongest
reasonable contrary case. Stop other expensive downstream work only when the
applicable research packet contains verified evidence that supports a stable
`Avoid` stance or funnel exclusion after those gates. An assumption, missing
field, generic sector label, proxy threshold, single ratio, or workload limit
is not an early-stop basis.

1. **Identity and basis:** legal entity, symbols, fiscal basis, segments,
   material subsidiaries, corporate actions, share count, and comparability.
2. **Business economics:** customer, product, purchase behavior, pricing,
   industry structure, competitive advantage, capital intensity, cyclicality,
   regulation, and concentration.
3. **Historical evidence:** preferably ten years and at least five when
   available; use shorter history without extrapolating it. Reconcile reported
   and normalized earnings, cash conversion, per-share growth, returns on
   capital, leverage, and dilution.
4. **Reinvestment and allocation:** deployable runway, incremental returns,
   capex, acquisitions, divestitures, debt, equity issuance, dividends,
   buybacks, and material value creation or destruction.
5. **Governance and resilience:** current auditor opinion/change, material
   exchange or regulatory actions, promoter ownership/pledge, related-party
   dealings, dilution, contingent liabilities, solvency, and sector-specific
   failure paths. Expand only where an issue is decision-relevant.
6. **Valuation and opportunity cost:** normalize the starting economics, test
   market-implied expectations, use two sector-appropriate valuation lenses,
   and compare bear/base/bull annualized total returns with the relevant TRI.
7. **Independent controls and synthesis:** reconcile the evidence audit, blind
   valuation replication, and strongest skeptic objections; then assign the
   stance and confidence supported at the cut-off.

Treat management statements as claims, not facts. Distinguish share-price
drawdown from permanent impairment. A severe drawdown affects position sizing
and holding suitability; permanent impairment means lasting destruction of
per-share intrinsic value through insolvency, forced destructive dilution,
fraud, governance failure, or structural loss of earning power.

## Evidence-gap rule

For every material gap record one of:

- `Decision-critical` — reasonable interpretations span incompatible stances
  and permitted retrieval is exhausted;
- `Material but bounded` — reasonable favorable and adverse assumptions or
  wider ranges still support a stance;
- `Non-critical` — useful but unlikely to change the stance; or
- `Monitoring` — a future condition with a named trigger.

Only the first can produce `Insufficient Evidence`. A missing field, short
provider history, thin MCP response, or lack of duplicate sourcing is not by
itself decision-critical. Never impute zero, a failed screen, or a negative
company fact from absence. When an MCP cannot resolve a required fact,
permitted retrieval includes targeted native web search and original-source
inspection. Stop retrieval when the claim is resolved, reasonable favorable
and adverse interpretations leave the stance stable, or authoritative routes
are exhausted and the gap has been classified.

## Ratings and stances

Do not use a numeric quality score. Rate business quality separately:

- `Exceptional` — durable advantage, strong reinvestment economics, resilient
  finances, and sound stewardship;
- `Strong` — attractive economics with bounded limitations;
- `Adequate` — investable economics may exist, but durability or runway is
  materially less certain;
- `Weak` — supported structural economics, stewardship, or resilience problem;
- `Unknown` — evidence cannot support a business-quality judgment.

Assign one investment stance only after focused research:

| Stance | Required meaning |
| --- | --- |
| `Investable Now` | Non-price risks are acceptable under the declared appetite, base return clears the risk-adjusted hurdle, downside fits the recorded loss tolerance, and the conclusion survives reasonable adverse assumptions. |
| `Attractive at Lower Price` | Business and non-price risks are acceptable, but current expected return is inadequate; state the approximate price zone and assumptions that would clear the hurdle. |
| `Watch / Needs Evidence` | The thesis is plausible, but a material uncertainty, disagreement, or changing condition prevents a current investable or avoid conclusion. State the exact issue and how each plausible resolution changes the stance. |
| `Avoid` | Verified governance, liquidity, solvency, structural business-quality, permanent-loss, or downside-asymmetry evidence makes ownership unattractive. State the controlling reason. |
| `Insufficient Evidence` | Exhausted decision-critical evidence prevents any defensible investment stance. State the missing fact and the incompatible outcomes it spans. |

Confidence is separate: `High`, `Moderate`, or `Low`. Confidence describes the
stability of the stance, not the quality of the company. Low confidence is not
an automatic veto when reasonable, risk-calibrated assumptions still support
the stance.

Screening dispositions in broad-universe work are only `Advance`, `Watch`, and
`Exclude from focused research`:

- `Advance` — the completed packet supports a plausibly competitive positive,
  contrarian, or opportunity-cost case that deserves focused work;
- `Watch` — a material unresolved fact or changing condition still has
  meaningful decision value; and
- `Exclude from focused research` — cited economics, valuation, risk, or
  opportunity-cost evidence makes deeper work lower value after the primary
  has tested the strongest reasonable contrary case.

These are funnel dispositions, not investment stances. Never present an
exclusion as `Avoid` unless focused research separately supports that stance.
A decision-critical gap cannot support exclusion.

## Valuation standard

Use valuation methods that match the economics: normalized earnings or FCF,
reverse DCF/expectations, DCF, sustainable ROE and price-to-book, residual
income, SOTP, dividend model, or mid-cycle valuation as appropriate. One of the
two lenses may be a reverse-expectations test; do not force two elaborate DCFs.

For each decision-relevant model record:

- normalized starting metric, exceptional-item treatment, share basis, and
  current price/date;
- explicit formulas with units, causal bear/base/bull operating assumptions,
  reinvestment and financing needs, and terminal economics;
- dated dividends where material, without double counting;
- nominal annualized total return, relevant TRI range, risk premium, declared
  risk-appetite calibration, and hurdle comparison;
- the highest-impact assumption and rounded breakpoint that changes the
  stance, plus joint sensitivity for interacting high-impact assumptions; and
- each method's value or price range and any material disagreement.

Do not mechanically average disagreeing methods. Explain the economic cause,
test the disputed assumption, and use the conclusion supported across the
declared risk-calibrated range; do not mechanically default to the most
pessimistic output. Use broad price zones, not false-precision targets.
Historical growth is evidence, not an automatic forecast; normalize cyclicals,
restructurings, financial institutions, acquisitions, and distorted base years
explicitly. Do not probability-weight scenarios unless the probabilities and
their comparable empirical or explicitly reasoned basis are recorded. Always
compare the primary model with the blind valuation-auditor reconstruction;
material differences require a lead resolution rather than averaging.

## Evidence ledger contract

The active run's append-only `research_evidence` rows contain one JSON payload
per record. Each payload has
`record_type`, `record_id`, `run_id`, `as_of`, and the fields required below.
IDs are immutable and unique. Source IDs use `S001`, `S002`, and so on;
independent evidence lineages use stable IDs such as `L001`.

| `record_type` | Required payload |
| --- | --- |
| `run` | status, execution mode, completed keys, remaining keys, and update time |
| `question` | decision question, horizon, outcome/decision affected, materiality threshold, and registration/amendment time |
| `hypothesis` | company/scope, proposition, strongest alternative, supporting observation, falsifier, horizon, status, and linked claim IDs |
| `source` | source ID, retrieval route, discovery query/purpose, title, direct URL, publisher, source tier/type, lineage ID/origin, independence, publication date, underlying data/event date, access time, and covered claims |
| `retrieval` | route, company/scope, query/purpose, attempted authority/source, status, failure reason, affected claim, and resulting source IDs |
| `company` | legal name, symbols, sector, basis, fiscal year, corporate-action status, and identity confidence |
| `metric` | company, metric, value, unit, period, basis, definition, normalization status, formula if derived, and source IDs |
| `claim` | company/scope, falsifiable claim text, fact/management claim/estimate/calculation/inference label, decision relevance, supporting and contradicting source IDs and lineage IDs, authority/directness/freshness assessment, counter-test, and confidence |
| `screen` | company, research-packet status, baseline-pass status, enrichment-pass status, common-basis comparison status, sector-appropriate signals, MCP coverage, targeted-web gap closure, source IDs, strongest positive and negative cases, conflicts and gaps, disposition, exclusion-gate result, controlling evidence, strongest contrary case, and primary-authored reason |
| `model` | company, method/scenario, formulas, inputs, assumptions, outputs, benchmark/hurdle, sensitivity, and source IDs |
| `audit` | audit role and mode, scope/company, audited record IDs, check/finding, severity, evidence, independent output where applicable, unresolved issue, plausible decision effect, and lead resolution |
| `skeptic` | company/scope, objection, severity, evidence, unresolved issue, and lead resolution |
| `forecast` | company, measurable outcome, metric definition, expected range, evaluation date, source/assumption basis, and thesis implication |
| `decision` | business rating, investment stance where eligible, confidence, price/evidence condition, and controlling reason |
| `validation` | check name, `Pass`/`Partial`/`Fail`, evidence, and effect on the conclusion |
| `ptc` | stage, program ID, eligible tools, call statuses/retries, normalized records, validation warnings, result status, and fallback status |

Do not save raw document dumps or duplicate source ledgers. Extract only
decision-used facts, compact screening metrics, retrieval failures, model
inputs, and audit findings. Append amendments and lead resolutions; never
silently overwrite a pre-registered hypothesis or conflict. Update `run`
records as checkpoints so an interrupted run resumes from this ledger without
separate progress files.

## Report standard

The active run's `research_runs.report_md` is a concise investment-committee
memo stored in Midas DB, not a chronology of the
research process or a dossier dump. Use only the applicable sections:

1. Executive Decision Summary
2. Scope, Cut-off, and Evidence Quality
3. Screening or Comparative Results
4. Company Decision Cases
5. Independent Audits, Skeptic Findings, and Resolutions
6. Valuation, Risks, and Price/Evidence Conditions
7. Final Conclusion
8. Decisive Sources and Limitations

For each focused company include: business rating, stance, confidence, variant
view, decisive evidence, evidence against, normalized economics, valuation
range, bear path, controlling assumption, closest alternative, mandate fit,
thesis invalidation trigger, and dated monitoring forecasts. Distinguish Midas
baseline coverage from native-web enrichment and disclose material unresolved
web gaps. Summarize evidence-audit exceptions, primary-versus-blind valuation
differences, and their lead resolutions. Cite decision-driving facts and model
inputs with source IDs and direct Markdown links. Background prose does not
need repetitive citations.

If no company is `Investable Now`, say so and identify the best-supported
researched candidate plus its controlling price or evidence condition. Do not
imply that a broad-universe winner was proven when only a subset received
focused work.

Label the output as an investment-research assessment, not personalized advice.
Never instruct the user to buy or sell a security.

Persist the report only with `research_run_set_report` or
`research_run_complete`. An intermediate report file is allowed, but the DB
report is the canonical final report; do not substitute a PDF, workbook, or
filesystem file for it.

## Publication checks

Record each check once as a `validation` record and summarize failures in the
report. Publication is blocked by an unresolved conflict in a decision-driving
price, unit, period, share count, formula, return, source, stance, or identity.

1. Identity, financial basis, corporate actions, dates, and units reconcile.
2. Every decision-driving fact and model input has usable provenance, source
   lineage, and a cut-off-compliant publication date.
3. Calculations are reproducible and scenario outputs match their inputs.
4. Missing data was not treated as negative evidence or a numeric zero.
5. Material source conflicts and valuation-method disagreements are resolved
   or constrain the stance explicitly.
6. Normalization, dilution, dividends, and TRI comparison are internally
   consistent.
7. Every material evidence-audit finding, blind-valuation difference, and
   skeptic objection has a lead resolution or remains visible and constrains
   the conclusion.
8. Business rating, investment stance, confidence, report summary, and final
   conclusion agree.
9. Every company has a targeted-web gap-closure record for material facts its
   MCP packet could not determine, or an explicit tool/source limitation with
   decision impact; focused companies complete the full applicable
   high-value enrichment review.
10. Every broad-universe exclusion has a complete or explicitly bounded
    minimum packet; completed baseline, enrichment, and common-basis comparison
    passes; cited controlling evidence; original-source inspection of the
    controlling reason and contrary case; and a primary-authored rationale.
    Missingness and workload are never the reason.
11. The report preserves the user's risk appetite and applies it consistently
    without changing objective business quality or excusing permanent-loss
    evidence.
12. Every external research fact came through an exposed Midas MCP or the
    native web-search/open/find/PDF route; calculations use only those retrieved
    inputs, and no prohibited retrieval route supplied evidence.
13. The registered question, hypotheses, alternatives, falsifiers, and later
    amendments are present; the report does not retrofit the original thesis to
    the observed evidence.
14. Source-count claims reflect independent lineages, positive and adverse
    claims received symmetric counter-tests, and failed searches were not
    treated as proof of absence.
15. Required evidence-auditor, valuation-auditor, and skeptic controls ran with
    the prescribed isolation and blinding, or the mandate names the exact
    capability failure and corresponding `self-*` execution.
16. Every focused company has dated, measurable monitoring forecasts and thesis
    implications without presenting future outcomes as cut-off evidence.

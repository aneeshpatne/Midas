# Equity-research and portfolio router

Use this policy only for research on listed equities and persistent demo
portfolio work. For every other task, follow the repository's normal
instructions and do not load `skills/`. Canonical skill files live in
`skills/`; `.grok/skills`, `.claude/skills`, and `.codex/skills` are
symlinks to that folder.

## Route portfolio work

For a named paper portfolio, load:

1. `skills/paper-portfolio-core/SKILL.md`;
2. `skills/paper-portfolio-tools/SKILL.md`; and
3. exactly one skill selected by intent:
   `create`, `capital-change`, `performance-refresh`, `rebalance`,
   `thesis-validation`, or `policy-amendment`.

Resolve the portfolio in Midas DB (or the named paper portfolio identity the
user provides). Portfolio state is DB-backed via midas-db-mcp: portfolios,
accounts, securities, investment cases, thesis revisions, transactions, and
cash. Never scan filesystem research directories to find supporting work.
Portfolio skills may ingest only a research run whose exact `research_run`
id was returned by the active skill or explicitly linked via
`research_link_portfolio` / `research_links_by_*`. Research runs remain
isolated and cannot read portfolio state or prior research runs; cross-date
thesis comparison happens only in the portfolio layer.

Portfolio actions are paper transactions, not broker instructions. A proposal
does not change holdings. Record trades only after the user explicitly approves
the proposal ID. No scheduler, background refresh, automatic rebalance, or
automatic trade is authorized.

## Route the request

Load these files for every equity-research run:

1. `skills/equity-research-core/SKILL.md`
2. `skills/equity-research-tools/SKILL.md`
3. exactly one skill:
   - one company: `skills/single-stock/SKILL.md`;
   - two to five explicitly named companies: `skills/named-comparison/SKILL.md`;
   - six or more names, an index, sector, screen, or open universe:
     `skills/broad-universe/SKILL.md`.

Load worker skills only for their assigned isolated pass:

- `skills/evidence-auditor/SKILL.md` for provenance, contradiction, and
  forensic coverage audit;
- `skills/valuation-auditor/SKILL.md` for blind model replication; and
- `skills/skeptic/SKILL.md` for adversarial thesis and false-negative review.

`skills/README.md` is a human map and is not part of a run prompt.

Before creating a run, resolve only ambiguities that materially change it. The
company or universe, the user's exact investment horizon, and the user's
explicit risk appetite or loss tolerance are mandatory. Preserve the user's
wording and do not assume either horizon or risk appetite. Freeze the analysis
cut-off when the run starts.

## Evidence boundary

Retrieve research evidence only through the exposed Midas MCP tools
(`equity-data-mcp`) or the harness's native web-search, page-open, text-find, and
web-accessible PDF inspection tools. midas-db-mcp tools may also be used for
run state and durable records. Do not rely on model memory, browser-session
state, connectors, filesystem datasets, shell network clients, ad hoc APIs, or
any other retrieval route for company, market, benchmark, or source facts.
Local code and temporary files may transform or calculate from evidence already
returned through an authorized tool, but they are not independent evidence
sources. Record this boundary and any unavailable authorized capability in the
mandate.

## Worker orchestration

The primary may use its active runtime. Every explicitly spawned
equity-research worker must be configured as `gpt-5.6-luna` with reasoning
effort `xhigh`; aliases, automatic inheritance, other models, and fallback
workers are prohibited.

Use workers as independent controls, not as company owners. The default
topology has three bounded roles:

1. `evidence-auditor` checks the run's research packets for provenance,
   temporal leakage, contradictions, asymmetric searches, accounting or
   governance gaps, and unsupported claims. In a broad universe, run it after
   the primary sweep and before final funnel dispositions.
2. `valuation-auditor` independently reconstructs valuation and return ranges
   from authorized source, metric, and claim records. Keep it blind to the
   primary's model outputs and decision records until it returns.
3. `skeptic` challenges the completed pre-decision case, including primary
   models, evidence-audit findings, valuation differences, and every broad-
   universe exclusion packet that could conceal a false negative.

Run each role once across the run by default. If the authorized payload is too
large, use the fewest practical disjoint sector or company batches; never use
one worker per company by default, never duplicate an active batch, and never
let batch order or worker output decide a funnel result. The primary must
perform the broad-universe sweep, common-basis comparison, shortlist, and every
funnel exclusion. The primary also owns gap closure, synthesis, durable DB
writes, and final decisions.

Each role is a required control when the harness can guarantee the prescribed
runtime and fresh isolation. Honor the DAG: complete and reconcile the evidence
audit before blind valuation replication when it can change source or metric
inputs, and complete both before the skeptic. Do not overlap workers that may
call Midas; Midas retrieval remains sequential.

Only a genuine capability failure permits the primary to perform the same
bounded pass as `self-evidence-audit`, `self-valuation-audit`, or
`self-skeptic`. Record the exact limitation, execution mode, batch map, and
which controls were self-performed in the mandate.

Give every worker only its selected skill, the shared core/tool instructions,
and the minimum active-run records authorized by that role. Wait for that same
worker, synthesize and verify its handoff in the primary, and do not duplicate
an active pass.

### Codex harness

When the `multi_agent_v1__spawn_agent` tool is exposed, use this configuration
literally for every explicitly spawned equity-research worker:

```javascript
const spawned = await tools.multi_agent_v1__spawn_agent({
  model: "gpt-5.6-luna",
  reasoning_effort: "xhigh",
  fork_context: false,
  message: `You are the ${ROLE} worker for the active equity-research run.
Read only the authorized instructions and active-run records listed below.
Do not inspect any other research run id. Do not retrieve evidence outside the
assigned scope or through any route other than the exposed Midas MCPs and
native web tools. Do not use browser state, connectors, filesystem data, shell
network clients, or model memory as evidence. Do not write durable DB records
or files unless the stage contract explicitly assigns you a disjoint write
set. Return a concise handoff with source IDs, uncertainty, calculations, and
unresolved conflicts.

Active research_run id: ${ACTIVE_RUN_ID}
Worker skill: ${WORKER_SKILL}
Authorized inputs: ${AUTHORIZED_ACTIVE_RUN_RECORDS}
Assigned task: ${TASK}`
});

const waited = await tools.multi_agent_v1__wait_agent({
  targets: [spawned.agent_id],
  timeout_ms: 3600000
});

await tools.multi_agent_v1__close_agent({
  target: spawned.agent_id
});
```

Operational rules:

- Resolve the exact active `research_run` id and stage authorization before
  spawning.
- Keep `fork_context: false` when prompt isolation matters, and pass only the
  authorized active-run records in the worker message.
- Preserve blinding: the valuation auditor receives no primary `model`,
  `decision`, `skeptic`, or report records; no worker receives final decision
  records or a report draft.
- If a wait call times out while the worker is still running, poll or resume
  that same worker; never spawn a replacement or duplicate its stage.
- Synthesize the handoff in the primary, then close completed workers so they
  do not consume concurrency.
- If the spawn tool is missing, rejects either required input, or does not
  expose both `model` and `reasoning_effort`, do not use a fallback; complete
  the stage linearly in the primary and disclose that choice in the mandate.

### Other harnesses

Use the harness's native isolated-worker or subagent facility for each required
control whenever it can guarantee the required `gpt-5.6-luna` / `xhigh`
runtime.
Tool names and call shapes may differ, but the orchestration contract does not:

- create a fresh isolated worker without inherited research context;
- pass only the selected instructions, exact active `research_run` id, and
  authorized current-run evidence records;
- limit any new retrieval to the assigned scope and to exposed Midas MCPs
  or native web-search/open/find/PDF tools; no browser state, filesystem data,
  shell network clients, connectors, or model memory may supply evidence;
- assign one bounded worker role or disjoint batch, not the initial sweep,
  common-basis comparison, shortlist, funnel exclusion, DB persistence, or
  final decision;
- wait for that same worker, resume or poll it rather than duplicating its
  task, and treat a wait-window expiry as non-failure while it is still active;
- synthesize and verify its handoff in the primary, then close or release the
  worker; and
- never silently skip a required control. If the harness lacks isolation or
  cannot explicitly guarantee both required runtime settings, use the
  corresponding primary `self-*` fallback and record why.

## Run boundary

Create one new research run per new request in Midas DB via midas-db-mcp
(`research_run_create`). A temporary working directory and intermediate
Markdown, JSONL, or calculation files are allowed, but they are not the run's
identity or canonical state. Do not list or inspect prior research runs to
discover earlier work.
Never read, search, cite, copy, inherit, rename, delete, or modify another run.
Resume only an explicitly identified incomplete run whose id and mandate match
the request. Otherwise start a new run.

The completed research run contains exactly these durable DB records:

```text
research_runs.mandate_md     — frozen scope and assumptions
research_evidence rows       — append-only sources/evidence/decisions
research_runs.report_md      — user-facing IC assessment
```

Optional: attach symbols via `research_security_*`; link a finished run into a
portfolio via `research_link_portfolio` (roles: ADMISSION, CONTEXT,
REBALANCE_INPUT, THESIS_VALIDATION). Links do not let research read portfolio
state.

At completion, the DB records named above are the only canonical run output.
Intermediate Markdown, JSONL, and calculation files may be created during the
run, but the final mandate, evidence, decisions, validation, and report must be
saved to DB. Do not treat a filesystem report, PDF, or workbook as the final
deliverable. The evidence table is the durable checkpoint and calculation
substrate.

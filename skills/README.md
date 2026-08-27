# Lean equity-research and paper-portfolio skills

This directory is the canonical instruction set for Indian listed-equity
research and persistent paper portfolios. Harness-specific directories
`.grok/skills`, `.claude/skills`, and `.codex/skills` are symlinks to this
folder.

It is designed to produce an auditable investment-committee memo without
stage-by-stage prompt duplication or artifact sprawl. The paper-portfolio
layer consumes exact, completed research decisions without weakening
research-run isolation and maintains frontend-friendly policy, event, and
state records in Midas DB.

## Runtime loading map

| Skill | Owner |
| --- | --- |
| `../AGENTS.md` | routing, harness-specific worker orchestration, and run isolation |
| `equity-research-core` | research judgment, classifications, valuation, and validation |
| `equity-research-tools` | evidence retrieval and provenance |
| `single-stock` | one-company flow |
| `named-comparison` | two-to-five-company flow |
| `broad-universe` | primary all-company sweep, evidence-backed funnel, and adaptive deep dives |
| `evidence-auditor` | isolated provenance, contradiction, and forensic coverage audit |
| `valuation-auditor` | blind independent valuation and return replication |
| `skeptic` | isolated thesis and false-negative challenge pass |
| `paper-portfolio-core` | portfolio policy, state, accounting, and approval contract |
| `paper-portfolio-tools` | prices, classifications, costs, research links, and DB persistence |
| `create`, `capital-change`, `performance-refresh`, `rebalance`, `thesis-validation`, `policy-amendment` | one selected persistent-portfolio action |

Load only the shared skills and selected action skill named by the root router.
Each normative rule has one owner; action skills specialize rather than
repeat shared policy.

## Output contract

Every completed run has three durable Midas DB records (not filesystem files):

- `research_runs.mandate_md` — frozen scope and assumptions;
- `research_evidence` rows — sources, evidence, calculations, challenge, decisions,
  and validation (append-only); and
- `research_runs.report_md` — the user-facing investment-committee assessment.

Optional portfolio links live in `research_portfolio_links` and never feed back
into an isolated research run.

The report is investment research, not personalized buy/sell advice. Missing
data is uncertainty, not adverse evidence. A high-quality but expensive company
is distinguished from a weak or unsafe business.

## Portfolio output contract

Each named portfolio is DB-backed in Midas DB (via midas-db-mcp), with:

- `portfolios` — policy-facing metadata and planned `target_capital_paise`;
- `transactions` — cash ledger (`cash_effect_paise`) and trade history;
- `investment_cases` + `thesis_revisions` — thesis lifecycle per security;
- optional `research_portfolio_links` — admission/context from research runs.

Legacy filesystem `portfolio/<slug>/` artifacts are not canonical for new
work. Intermediate Markdown, JSONL, and calculation files are allowed, but all
final portfolio and research state must be persisted in Midas DB. A PDF,
workbook, or filesystem report is not the final deliverable.

## Example creation prompts

```text
Create a portfolio called Large Cap Demo with ₹1 lakh. My risk appetite is
moderate: avoid excessive concentration, keep up to 20% cash when valuation is
poor, research Indian large-cap companies first, and propose the portfolio.

Create a portfolio called Quality Compounders with ₹10 lakh. Use a five-year
horizon, Indian listed stocks only, 60% large / 25% mid / 15% small, and do
fresh research before proposing holdings.
```

These create funded paper accounts and researched `Draft` proposals. They do
not record holdings until the user approves the returned proposal ID.

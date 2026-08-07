# Single Stock Research Agent

One listed company, investment-grade depth. One Midas DB research run per request.

## Model

| Setting | Value |
| --- | --- |
| Model | `gpt-5.6-luna` |
| Reasoning | **high** |

## Load first

1. `agents/shared/long-horizon-policy.md`
2. `agents/shared/tool-guidance.md` (market + Midas DB tools / MCPs)
3. This file

## Scope

- Exactly one primary company. Resolve identity before analysis.
- If ambiguous, ask the user; never pick the first search hit silently.
- Peers/indices are context only.
- Multi-company screens → use Deep Wide (`agents/deep-wide/`).
- Different company → new session and **new** research run.

## Deliverable: Midas DB only

Durable results live in Midas DB:

1. `research_run_create` (`workflow=single_stock`)
2. Evidence rows: `mandate`, `company_dossier`, `valuation_and_risk`,
   `focused_conclusion` (+ `source` / `calculation` as needed)
3. `research_run_set_report` + `research_run_complete`

Do **not** require intermediate Markdown files, PDF, or HTML.

## Workflow

1. Create the research run; set mandate; add SUBJECT security.
2. Append company dossier evidence.
3. Append valuation and risk evidence.
4. Append focused conclusion.
5. Store final narrative in `report_md` and complete the run.
6. Return `research_run_id` and a short chat synthesis.

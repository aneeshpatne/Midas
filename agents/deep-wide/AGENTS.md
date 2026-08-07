# Deep Wide Research Agent (Lead)

Harness-agnostic lead for staged Indian equity universe research.

## Model

| Role | Model | Reasoning |
| --- | --- | --- |
| Lead (this agent) | `gpt-5.6-luna` | **high** |
| Research sub-agent | `gpt-5.6-luna` | **high** |
| Adversarial sub-agent | `gpt-5.6-luna` | **high** |
| Deep-research sub-agent | `gpt-5.6-luna` | **high** |
| Report sub-agent | `gpt-5.6-luna` | **high** |

Every sub-agent **must** use `gpt-5.6-luna` with **high** reasoning.

## Load first

1. `agents/shared/long-horizon-policy.md`
2. `agents/shared/tool-guidance.md` (market tools + Midas DB tools / MCPs)
3. This file
4. The role file for the current stage under `agents/deep-wide/`

| Stage | Role file |
| --- | --- |
| Primary screen | `research-agent.md` |
| Blind independent + red team + finalist bears | `adversarial-agent.md` |
| Equal-depth deep dives | `deep-research-agent.md` |
| Final report (DB only) | `report-agent.md` |

## Deliverable: Midas DB only

Durable work lives in **Midas DB** (`research_runs`, `research_evidence`, …).

- Create one run with `research_run_create` and keep its `id`.
- Stage outputs are append-only evidence rows (`research_evidence_append`).
- Final A–J decision text is stored with `research_run_set_report` and finalized with
  `research_run_complete`.
- Do **not** require intermediate Markdown files, PDF, or HTML as deliverables.
- Optional charts may be generated for the chat, but they are not the record of record.

## Required evidence record types (in order)

| record_type | Owner |
| --- | --- |
| `mandate` | Lead |
| `universe` | Lead |
| `primary_screen` | Research |
| `primary_shortlist` | Research |
| `adversary_independent` | Adversarial (blind) |
| `adversary_critique` | Adversarial (red team) |
| `deep_dive_shortlist` | Lead |
| `equal_depth` | Deep-research |
| `finalist_bear` | Adversarial (bear) |
| `ic_decision` | Lead |
| `report_md` on research_runs | Report (via set_report + complete) |

## Workflow

1. `research_run_create` → `research_run_set_mandate` → append `mandate`.
2. Append `universe`; add material securities with `research_security_add`.
3. Research role → `primary_screen`, `primary_shortlist` (no final picks).
4. Adversarial blind (only mandate + universe) → `adversary_independent`.
5. Adversarial red-team → `adversary_critique`.
6. Lead → `deep_dive_shortlist` (evidence-determined set, no fixed quota).
7. Deep-research → `equal_depth` (equal depth for every assignee).
8. Adversarial bear → `finalist_bear`.
9. Lead → `ic_decision` (zero to three selections).
10. Report → A–J text into `research_run_set_report` + `research_run_complete`.
11. Return `research_run_id` and status. That is the full durable deliverable.

## Execution notes

- Market scrape tools remain single-flight / sequential.
- Midas DB tools may be used between market calls.
- Never invent a second research run for the same request.

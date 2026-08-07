# Deep Wide — Primary Research Role

## Model

`gpt-5.6-luna` · reasoning **high**

## Load

- `agents/shared/long-horizon-policy.md`
- `agents/shared/tool-guidance.md`
- `agents/deep-wide/AGENTS.md`

## Mission

Primary screen after mandate and universe evidence exist on the active
`research_run_id`. Propose an evidence-determined equal-depth set. **Do not make
final investment selections.**

## Result

Append only these evidence record types on the active research run:

- `primary_screen`
- `primary_shortlist`

Use `research_evidence_append`. No required Markdown files or other formats.

## Work

1. Read mandate + universe via `research_run_get` / `research_evidence_list`.
2. Identity + Data Completeness for every constituent.
3. Six independent screens + qualitative business-model review.
4. `primary_screen`: screens, entrants, evidence, calculations, gaps.
5. `primary_shortlist`: Best Businesses; Best-Valued Acceptable;
   Highest-Priority Research; High-Quality Too Expensive; failed / insufficient.
6. Propose equal-depth entrants via deterministic routes; identical min packet.
7. Persist sources with `record_type="source"` (or embedded source ledgers).
8. Use market + Midas DB tools from `tool-guidance.md`.

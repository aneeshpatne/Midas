# Midas agent instructions (harness-agnostic)

Portable Markdown instructions for Indian long-horizon equity research.

## Model

Every agent and sub-agent: **`gpt-5.6-luna`** with **high** reasoning.

## MCPs

Only the market-info MCPs from `src/midas/mcp_server.py` — listed in
`shared/tool-guidance.md`. No other tools.

## Deliverable

**Markdown files only.** Each stage writes its named `.md` into a new run folder.
No HTML/PDF.

## Layout

```text
agents/
  README.md
  shared/
    long-horizon-policy.md    # research standard
    tool-guidance.md          # only mcp_server.py MCP names
  deep-wide/
    AGENTS.md                 # lead
    research-agent.md
    adversarial-agent.md
    deep-research-agent.md
    report-agent.md
  single-stock/
    AGENTS.md                 # merged one-company agent
```

## Which agent

| Intent | Load |
| --- | --- |
| Universe / index / multi-name | `deep-wide/AGENTS.md` + `shared/*` + role cards |
| One company | `single-stock/AGENTS.md` + `shared/*` |

## New folder every run

```text
research/<slug>/<UTC-YYYYMMDDTHHMMSSZ>/
```

Deep wide: `00_mandate.md` … `10_final_report.md`  
Single stock: `00_stock_mandate.md` … `03_focused_stock_conclusion.md`

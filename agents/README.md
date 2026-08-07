# Midas agent instructions (harness-agnostic)

Portable Markdown instructions for Indian long-horizon equity research.

## Model

Every agent and sub-agent: **`gpt-5.6-luna`** with **high** reasoning.

## Tools / MCPs

See `shared/tool-guidance.md`:

- **Market info** — `midas-mcp` / in-process scrape tools
- **Midas DB** — `midas-db-mcp` / in-process DB tools (research runs + paper portfolios)

DeepAgents load both via `MIDAS_TOOLS`.

## Deliverable

**Midas DB research runs** (evidence ledger + `report_md`). No required intermediate
Markdown files and no final PDF/HTML.

## Layout

```text
agents/
  README.md
  shared/
    long-horizon-policy.md    # research standard
    tool-guidance.md          # market + DB tools
  deep-wide/
    AGENTS.md                 # lead
    research-agent.md
    adversarial-agent.md
    deep-research-agent.md
    report-agent.md
  single-stock/
    AGENTS.md
```

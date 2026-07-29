# Midas

Midas searches the web, renders pages with Camoufox, extracts clean main-page text
locally, then compresses that scraped corpus with an Ollama model
(`gpt-oss:120b-cloud` by default) via ChatOpenAI's OpenAI-compatible client.

The model only compresses what was scraped. It is not asked to research beyond those
pages. Full cleaned page text remains available on each successful source.

## Setup

```bash
uv sync
uv run python -m camoufox fetch
cp .env.example .env
```

Compression talks to a local Ollama server at `http://localhost:11434/v1`. Make sure
Ollama is running and the model is available:

```bash
ollama pull gpt-oss:120b-cloud
```

Optional overrides in `.env`:

```dotenv
OLLAMA_BASE_URL=http://localhost:11434/v1
# OLLAMA_API_KEY=ollama
```

## Usage

Run the DeepAgent from the command line:

```bash
uv run midas "Summarize TCS's latest results and concall guidance"
uv run midas "NIFTY IT"
```

The CLI displays a compact status line for each research tool and `send_update`
research narration as they arrive, then prints the final answer. It needs the same
model credentials as the configured DeepAgent (`DEEPSEEK_API_KEY` by default); the
CLI automatically loads a project `.env` file.

For an interactive, Codex-style terminal session, launch the TUI:

```bash
uv run midas-tui
```

The TUI keeps conversational context in memory for follow-up questions and streams
agent text, provider-visible reasoning/status blocks, research updates, tool activity,
and todos as they happen. The agent panel highlights the lead, research, adversarial,
or report agent currently producing work. Markdown artifacts created during the
session appear under `output/research` in the file tree and can be selected for a
rendered preview.

Controls:

- `Enter` — submit the prompt.
- `Ctrl+C` — cancel active research, or quit while idle.
- `Ctrl+N` or `/new` — clear the conversation and start a fresh context.
- `F2` / `F3` — toggle the agents/todos and files/preview panes.
- `/quit` — exit.

The input is intentionally locked while a turn is running. TUI context is ephemeral
and is discarded on exit; generated research artifacts remain on disk. Both
`DEEPSEEK_API_KEY` and `OPENAI_API_KEY` should be configured for the complete staged
workflow. If either is missing, the interface still opens and displays a setup error.

For a sector or NSE index, Midas runs a staged 12–24 month idea-generation workflow:

1. A primary research agent screens the complete universe and writes its research,
   3–5 deeper-research candidates, and explicit elimination logic as Markdown.
2. An adversarial agent builds a blind competing screen, then runs a second pass
   challenging the primary selection.
3. The lead agent verifies disagreements and writes an auditable reconciliation and
   final shortlist.
4. A publication-only agent calls its single `generate_report` tool to compile the
   completed Markdown set into `final_report.pdf` with Tectonic.

Each run is saved under `output/research/<topic>/<timestamp>/`. The output is research
prioritization, not personalized investment advice or a buy/sell recommendation.

Call the whole pipeline with one helper:

```python
from midas import web_search

result = web_search(
    "Recent developments in sodium-ion batteries",
    max_results=5,
)
print(result.compressed)  # AI compression of scraped pages only
for source in result.sources:
    print(source.source_id, source.status, source.url)
    if source.content:
        print(source.content[:200])
```

Or from the command line:

```bash
uv run python examples/web_search.py "Recent developments in sodium-ion batteries"
uv run python examples/web_search.py "query" --max-results 3
```

In async code:

```python
from midas import search_and_scrape

result = await search_and_scrape("Recent developments in sodium-ion batteries")
```

The result is a frozen Pydantic model with the query, compressed text, and source
records. Successful sources include full cleaned `content`; failed pages include an
`error`. A failed page does not abort the pipeline when at least one other page succeeds.

## fundamentals provider company scraper

Midas also ships a structured scraper for
[`https://www.fundamentals provider/company/{symbol}/`](https://www.fundamentals provider/):

```python
from midas import scrape_company_sync

result = scrape_company_sync(
    "RELIANCE",
    include_chart=True,
    include_concalls=True,  # download latest transcript PDFs + Ollama summary
)
print(result.summary())
print(result.page.chart_insights.bullets)  # agent-friendly chart stats
print(result.page.concall_transcripts[0].summary)
print(result.agent_brief())                # markdown for an LLM
# or: result.agent_payload()               # compact JSON (no daily ticks)
```

CLI:

```bash
uv run python examples/scrape_fundamentals.py RELIANCE
uv run python examples/scrape_fundamentals.py TCS --chart             # + chart insights
uv run python examples/scrape_fundamentals.py TCS --concalls          # + transcript PDFs
uv run python examples/scrape_fundamentals.py TCS --concalls --no-concall-summary  # extract only
uv run python examples/scrape_fundamentals.py TCS --agent             # brief + chart + concalls
uv run python examples/scrape_fundamentals.py TCS --agent-json tcs_agent.json
uv run python examples/scrape_fundamentals.py TCS --consolidated --both --json tcs.json
uv run python examples/scrape_fundamentals.py --search "tata motors"
```

It extracts profile/ratios, pros & cons, sector path, quarterly + annual statements,
balance sheet, cash flow, ratios, growth CAGRs, shareholding, peers, announcements,
annual reports, credit ratings, and concall **links**. With `--chart` /
`include_chart=True`, it also pulls Price / 50-DMA / 200-DMA / Volume and derives
returns, drawdown, DMA regime, and volume stats for agents. With `--concalls` /
`include_concalls=True`, it downloads the latest transcript PDFs, extracts text, and
summarizes them with the same Ollama model used by web search (guidance, margins,
capex, risks, Q&A). Be polite with request volume.

## signals provider high-impact signals

Midas also scrapes **free, high-impact** pages on
[`signals provider`](https://signals provider/) that complement Screener (not a
fundamentals replacement):

- analyst consensus headline (target / upside / analyst count)
- SWOT rule-based strengths, weaknesses, opportunities, threats
- superstar (ace investor) holdings and recent buys/sells
- ASM/GSM surveillance risk flag
- FII/DII cash-segment snapshot

```python
from midas import scrape_signals_sync

result = scrape_signals_sync("TCS")
print(result.agent_brief())
print(result.agent_payload()["swot"])
```

CLI:

```bash
uv run python examples/scrape_signals.py TCS
uv run python examples/scrape_signals.py TCS --agent
uv run python examples/scrape_signals.py TITAN --json
uv run python examples/scrape_signals.py --superstars
uv run python examples/scrape_signals.py --asm
uv run python examples/scrape_signals.py --fii-dii
```

Be polite with request volume. Prefer Screener for statements/peers/concalls;
use signals provider for the signal layer above.

## DeepAgent tools

Expensive research tool results can be shared across runs through Redis. Set
`MIDAS_REDIS_URL` (or `REDIS_URL`) to a Redis connection URL such as
`redis://localhost:6379/0`. Successful scrape and market-data responses are cached
for 24 hours; errors are never cached, and Redis failures fall back to uncached
execution.

`midas.deepagents.deepagent.agent` automatically registers twenty-four tools:

- `send_update` — emits a conversational, real-time research update through the
  agent's custom stream.
- `web_research` — grounded web search, scrape, and summary with source URLs.
- `company_fundamentals` — normal Screener fundamentals, statements, peers, and chart data.
- `earnings_transcripts` — a separate transcript tool for management guidance, margins,
  capex, risks, and Q&A.
- `market_signals` — consensus, SWOT, superstars, ASM/GSM, FII/DII.
- `nse_list_index` — live constituents for Nifty and special NSE equity lists.
- `nse_company_filings` — NSE announcements, actions, board meetings, results,
  shareholding, and annual-report links.
- `nse_equity_snapshot` — live NSE quote, volume, delivery, price-band, 52-week,
  security-status, and identity context.
- `equity_trading_history` — bounded price, volatility, drawdown, volume, and
  delivery-trend analysis.
- `nse_market_scan` — index breadth, gainers, losers, volume gainers, active
  equities, and India VIX.
- `equity_event_calendar` — market-wide or symbol-filtered results and corporate
  event discovery.
- `exchange_deals` — bulk deals, block deals, and reported short-selling activity.
- `nse_derivatives_snapshot` — bounded option-chain positioning, PCR, max pain,
  major OI strikes, lot size, and F&O-ban status.
- `institutional_activity` — latest or dated FII/DII, NSDL FPI, and derivatives reports.
- `india_market_context` — compact Nifty price/TRI and MCX commodity performance.
- `twitter_search` — latest public X/Twitter discussion through the local Grok CLI,
  capped at two calls per agent instance.
- `generate_bar_chart` / `generate_horizontal_bar_chart` — static PNG bar charts.
- `generate_line_chart` / `generate_area_chart` — single- or multi-series trend charts.
- `generate_pie_chart` — non-negative labelled-share charts.
- `generate_stacked_bar_chart` — multi-series composition by category.
- `generate_scatter_chart` — labelled x/y observation plots.
- `generate_heatmap_chart` — numeric row/column matrix visualizations.

Chart artifacts are written to `output/charts/` and the tools return JSON containing
the absolute path, relative path, Markdown embed, and a note that the values are
rendered as supplied rather than independently verified.

Set `DEEPSEEK_API_KEY` before importing the configured agent, then invoke it as usual:

```python
from midas.deepagents.deepagent import agent

answer = await agent.ainvoke(
    {"messages": [("user", "Summarize TCS's latest results and concall guidance")]}
)
```

To render progress updates as they happen, stream the agent with the `custom` mode
and handle chunks whose `type` is `deep_agent_update`:

```python
async for mode, chunk in agent.astream(
    {"messages": [("user", "Research TCS")],},
    stream_mode=["updates", "custom"],
):
    if mode == "custom" and chunk["type"] == "deep_agent_update":
        print(chunk["update"])
```

`twitter_search` requires the `grok` CLI on `PATH`; unavailable CLI, timeout, and
non-zero exit failures are returned to the agent as structured errors.

## Development

```bash
uv run ruff check .
uv run pytest
```

The optional browser smoke test requires an installed Camoufox browser and network
access:

```bash
MIDAS_RUN_INTEGRATION=1 uv run pytest -m integration
```

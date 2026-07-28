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

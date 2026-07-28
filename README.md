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

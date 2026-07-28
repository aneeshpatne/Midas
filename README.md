# Midas

Midas exposes one asynchronous utility that searches the web, renders pages with
Camoufox, extracts clean main-page text locally, and compresses the cleaned corpus
with `gpt-5.6-terra`.

Raw HTML, search-result snippets, scripts, and unfiltered DOM text are not sent to
the model.

## Setup

```bash
uv sync
uv run python -m camoufox fetch
cp .env.example .env
```

Add your OpenAI API key to `.env`:

```dotenv
OPENAI_API_KEY=your-api-key-here
```

## Usage

```python
import asyncio

from midas import search_scrape_compress


async def main() -> None:
    result = await search_scrape_compress(
        "Recent developments in sodium-ion batteries",
        max_results=5,
    )
    print(result.digest)
    for source in result.sources:
        print(source.source_id, source.status, source.url)


asyncio.run(main())
```

The result is a frozen Pydantic model containing the original query, the neutral
digest, and successful or failed source records. A failed page does not abort the
pipeline when at least one other page succeeds.

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

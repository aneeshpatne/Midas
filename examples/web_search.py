"""Run Midas web search, scrape, and compress from the command line.

Usage:
    uv run python examples/web_search.py "Recent developments in sodium-ion batteries"
    uv run python examples/web_search.py "query" --max-results 3
"""

from __future__ import annotations

import argparse
import sys

from midas import web_search


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Search, scrape, and compress cleaned page text with Ollama.",
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Number of search results to scrape (1-10, default: 5)",
    )
    args = parser.parse_args(argv)

    result = web_search(args.query, max_results=args.max_results)
    print(result.compressed)
    print()
    print("Sources:")
    for source in result.sources:
        line = f"  [{source.source_id}] {source.status.value}  {source.url}"
        if source.error:
            line += f"  ({source.error})"
        print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())

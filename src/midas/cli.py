"""Command-line entry point for the Midas DeepAgent."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Sequence
from typing import Any

from dotenv import load_dotenv


def _text_content(content: Any) -> str:
    """Convert LangChain's string or structured message content to display text."""
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence):
        return "\n".join(
            block["text"]
            for block in content
            if isinstance(block, dict)
            and isinstance(block.get("text"), str)
            and block.get("type", "text") == "text"
        )
    return str(content)


async def run_topic(topic: str, research_agent: Any) -> str:
    """Run one topic and print streaming progress updates, returning the final answer."""
    final_answer = ""
    async for mode, chunk in research_agent.astream(
        {"messages": [("user", topic)]},
        stream_mode=["updates", "custom"],
    ):
        if mode == "custom":
            if isinstance(chunk, dict) and chunk.get("type") == "deep_agent_update":
                print(f"\n[Research update]\n{chunk['update']}\n", flush=True)
            continue

        if mode != "updates" or not isinstance(chunk, dict):
            continue
        for node_update in chunk.values():
            if not isinstance(node_update, dict):
                continue
            for message in node_update.get("messages", []):
                tool_calls = getattr(message, "tool_calls", None)
                if tool_calls:
                    continue
                content = _text_content(getattr(message, "content", ""))
                if content:
                    final_answer = content

    if not final_answer:
        raise RuntimeError("The agent completed without a final text answer.")
    return final_answer


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="midas",
        description="Research a topic with the Midas DeepAgent.",
    )
    parser.add_argument("topic", help="The company, event, or research question to investigate.")
    return parser


def _configure_tool_logging() -> None:
    """Print semantic Midas tool logs without enabling noisy dependency logging."""
    tool_logger = logging.getLogger("midas.deepagents.tools")
    if not any(getattr(handler, "_midas_cli_handler", False) for handler in tool_logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._midas_cli_handler = True  # type: ignore[attr-defined]
        tool_logger.addHandler(handler)
    tool_logger.setLevel(logging.INFO)
    tool_logger.propagate = False


def main(argv: list[str] | None = None) -> int:
    """Run the Midas CLI and return a shell-compatible exit status."""
    args = _parser().parse_args(argv)
    load_dotenv()
    if not os.getenv("DEEPSEEK_API_KEY"):
        print(
            "midas: DEEPSEEK_API_KEY is not configured. Add it to .env or export it before "
            "running `uv run midas \"topic\"`.",
            file=sys.stderr,
        )
        return 2
    _configure_tool_logging()
    try:
        # Delay model construction until after argument parsing so `midas --help`
        # works without API credentials or a configured model provider.
        from .deepagents.deepagent import agent

        answer = asyncio.run(run_topic(args.topic, agent))
    except Exception as exc:
        print(f"midas: {exc}", file=sys.stderr)
        return 1

    print(answer)
    return 0

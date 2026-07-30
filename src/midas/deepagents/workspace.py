"""Per-invocation agent workspace context shared by host-side tools."""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

AGENT_OUTPUT_DIRECTORY: ContextVar[Path | None] = ContextVar(
    "midas_agent_output_directory", default=None
)


def agent_output_directory() -> Path:
    configured = AGENT_OUTPUT_DIRECTORY.get()
    return configured.resolve() if configured is not None else Path.cwd().resolve()


def has_isolated_agent_output_directory() -> bool:
    return AGENT_OUTPUT_DIRECTORY.get() is not None

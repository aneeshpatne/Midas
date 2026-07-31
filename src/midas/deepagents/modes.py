"""Stable research-mode metadata shared by agents, sessions, and the TUI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ResearchMode(StrEnum):
    """Top-level research workflows exposed by Midas."""

    DEEP_WIDE = "deep-wide"
    SINGLE_STOCK = "single-stock"


@dataclass(frozen=True, slots=True)
class ResearchModeSpec:
    """User-facing and graph-level metadata for one research mode."""

    label: str
    root_agent_id: str
    prompt_placeholder: str


DEEP_WIDE_ROOT_AGENT_ID = "deep-wide-research-agent"
SINGLE_STOCK_ROOT_AGENT_ID = "single-stock-research-agent"
LEGACY_ROOT_AGENT_ID = "midas-lead-analyst"
DEFAULT_RESEARCH_MODE = ResearchMode.DEEP_WIDE

RESEARCH_MODE_SPECS = {
    ResearchMode.DEEP_WIDE: ResearchModeSpec(
        label="Deep Wide Research Agent",
        root_agent_id=DEEP_WIDE_ROOT_AGENT_ID,
        prompt_placeholder="Ask about a sector, NSE index, or broad equity mandate…",
    ),
    ResearchMode.SINGLE_STOCK: ResearchModeSpec(
        label="Single Stock Research Agent",
        root_agent_id=SINGLE_STOCK_ROOT_AGENT_ID,
        prompt_placeholder="Enter one company name, symbol, or focused stock question…",
    ),
}


def normalize_research_mode(value: ResearchMode | str | None) -> ResearchMode:
    """Return a supported mode, defaulting safely for legacy stored values."""
    if isinstance(value, ResearchMode):
        return value
    try:
        return ResearchMode(value)
    except (TypeError, ValueError):
        return DEFAULT_RESEARCH_MODE


def research_mode_spec(mode: ResearchMode | str | None) -> ResearchModeSpec:
    """Return normalized metadata for a research mode."""
    return RESEARCH_MODE_SPECS[normalize_research_mode(mode)]


def next_research_mode(mode: ResearchMode | str | None) -> ResearchMode:
    """Toggle between the two top-level research modes."""
    current = normalize_research_mode(mode)
    if current == ResearchMode.DEEP_WIDE:
        return ResearchMode.SINGLE_STOCK
    return ResearchMode.DEEP_WIDE

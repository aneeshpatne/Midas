"""Chat model factories for the orchestrator, research agents, and specialists."""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from langchain_openrouter import ChatOpenRouter

_OPENROUTER_MODEL = "openai/gpt-5.6-luna"
_OPENROUTER_PROVIDER = {"order": ["OpenAI"]}


def _openrouter_model(*, reasoning_effort: str) -> ChatOpenRouter:
    """Build an OpenRouter chat model with OpenAI preferred routing."""
    return ChatOpenRouter(
        model=_OPENROUTER_MODEL,
        reasoning={"effort": reasoning_effort},
        openrouter_provider=_OPENROUTER_PROVIDER,
    )


def get_main_model() -> ChatOpenRouter:
    """Primary orchestrator model (OpenRouter).

    Uses ``openai/gpt-5.6-luna`` with medium reasoning and OpenAI as the preferred
    provider. Reads ``OPENROUTER_API_KEY`` from the environment via the library default.
    """
    return _openrouter_model(reasoning_effort="medium")


def get_research_model() -> ChatOpenRouter:
    """Research subagent model (OpenRouter).

    Used by research-agent and adversarial-agent for evidence gathering.
    Uses ``openai/gpt-5.6-luna`` with medium reasoning and OpenAI as the preferred
    provider. Reads ``OPENROUTER_API_KEY`` from the environment via the library default.
    """
    return _openrouter_model(reasoning_effort="medium")


def get_deep_research_model() -> ChatOpenRouter:
    """Dedicated model for the final-stage deep-research subagent.

    Uses ``openai/gpt-5.6-luna`` with high reasoning and OpenAI as the preferred
    provider. This separate factory lets the deep-dive model and reasoning
    configuration be tuned without changing the broad research and adversarial agents.
    Reads ``OPENROUTER_API_KEY`` from the environment via the library default.
    """
    return _openrouter_model(reasoning_effort="high")


def get_summarizer_model() -> ChatOpenRouter:
    """Report-writing subagent model (OpenRouter).

    Uses ``openai/gpt-5.6-luna`` with high reasoning and OpenAI as the preferred
    provider. Reads ``OPENROUTER_API_KEY`` from the environment via the library default.
    """
    return _openrouter_model(reasoning_effort="high")


def get_image_model() -> ChatOpenAI:
    """Vision model for reviewing ``search_image`` candidates (OpenAI).

    Uses GPT-5.6 Terra to open/view downloaded images and decide whether they
    are editorially good enough, or more should be requested.
    Reads ``OPENAI_API_KEY`` from the environment via the library default.
    """
    return ChatOpenAI(
        model="gpt-5.6-terra",
        use_responses_api=True,
        model_kwargs={"prompt_cache_key": "odin-search-image-vision"},
    )

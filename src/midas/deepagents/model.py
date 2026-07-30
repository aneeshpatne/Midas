"""Chat model factories for the orchestrator, research agents, and specialists."""

from __future__ import annotations

import os

from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI

_DEFAULT_COST_CONTEXT_TOKENS = 75_000


def _cost_bounded(model: ChatDeepSeek) -> ChatDeepSeek:
    """Use a cost window for DeepAgents compaction below provider capacity.

    DeepAgents derives its default 85%-trigger/10%-keep summarization settings
    from ``profile.max_input_tokens``. DeepSeek advertises a one-million-token
    provider window, which is technically valid but economically unsuitable for
    an iterative tool agent because the whole growing history is billed again on
    every step.
    """
    raw = os.getenv("MIDAS_CONTEXT_BUDGET_TOKENS", str(_DEFAULT_COST_CONTEXT_TOKENS))
    try:
        budget = max(24_000, int(raw))
    except ValueError:
        budget = _DEFAULT_COST_CONTEXT_TOKENS
    profile = dict(model.profile or {})
    provider_limit = profile.get("max_input_tokens")
    if isinstance(provider_limit, int):
        profile["provider_max_input_tokens"] = provider_limit
        budget = min(budget, provider_limit)
    profile["max_input_tokens"] = budget
    model.profile = profile
    return model


def get_main_model() -> ChatDeepSeek:
    """Primary orchestrator model (DeepSeek).

    Reads ``DEEPSEEK_API_KEY`` from the environment via the library default.
    """
    return _cost_bounded(
        ChatDeepSeek(
            model="deepseek-v4-flash",
            reasoning_effort="high",
        )
    )


def get_research_model() -> ChatDeepSeek:
    """Research subagent model (DeepSeek).

    Used by research-agent and adversarial-agent for evidence gathering.
    Reads ``DEEPSEEK_API_KEY`` from the environment via the library default.
    """
    return _cost_bounded(
        ChatDeepSeek(
            model="deepseek-v4-flash",
            reasoning_effort="high",
        )
    )


def get_deep_research_model() -> ChatDeepSeek:
    """Dedicated model for the final-stage deep-research subagent.

    This separate factory lets the deep-dive model and reasoning configuration be
    tuned without changing the broad research and adversarial agents.
    Reads ``DEEPSEEK_API_KEY`` from the environment via the library default.
    """
    return _cost_bounded(
        ChatDeepSeek(
            model="deepseek-v4-pro",
            reasoning_effort="high",
        )
    )


def get_summarizer_model() -> ChatDeepSeek:
    """Report-writing subagent model (DeepSeek).

    Reads ``DEEPSEEK_API_KEY`` from the environment via the library default.
    """
    return _cost_bounded(
        ChatDeepSeek(
            model="deepseek-v4-pro",
            reasoning_effort="high",
        )
    )


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

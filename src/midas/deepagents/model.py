"""Chat model factories for the orchestrator, research agents, and specialists."""

from __future__ import annotations

from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI


def get_main_model() -> ChatDeepSeek:
    """Primary orchestrator model (DeepSeek).

    Reads ``DEEPSEEK_API_KEY`` from the environment via the library default.
    """
    return ChatDeepSeek(
        model="deepseek-v4-flash",
        reasoning_effort="high",
    )


def get_research_model() -> ChatDeepSeek:
    """Research subagent model (DeepSeek).

    Used by research-agent and adversarial-agent for evidence gathering.
    Reads ``DEEPSEEK_API_KEY`` from the environment via the library default.
    """
    return ChatDeepSeek(
        model="deepseek-v4-flash",
        reasoning_effort="high",
    )


def get_deep_research_model() -> ChatDeepSeek:
    """Dedicated model for the final-stage deep-research subagent.

    This separate factory lets the deep-dive model and reasoning configuration be
    tuned without changing the broad research and adversarial agents.
    Reads ``DEEPSEEK_API_KEY`` from the environment via the library default.
    """
    return ChatDeepSeek(
        model="deepseek-v4-pro",
        reasoning_effort="high",
    )


def get_summarizer_model() -> ChatDeepSeek:
    """Report-writing subagent model (DeepSeek).

    Reads ``DEEPSEEK_API_KEY`` from the environment via the library default.
    """
    return ChatDeepSeek(
        model="deepseek-v4-pro",
        reasoning_effort="high",
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

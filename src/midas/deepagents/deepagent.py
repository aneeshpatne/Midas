from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission
from langchain.agents import create_agent

from .model import get_main_model, get_research_model, get_summarizer_model
from .prompts import (
    ADVERSARIAL_AGENT_PROMPT,
    MIDAS_PRIMARY_SYSTEM_PROMPT,
    REPORT_AGENT_PROMPT,
    RESEARCH_AGENT_PROMPT,
)
from .reporting import REPORT_TOOLS
from .tools import MIDAS_TOOLS

MIDAS_TOOL_GUIDANCE = """Use the available research tools to gather evidence before
making factual claims.
Prefer Screener for company fundamentals, financial statements, peers, and earnings
calls; use signals provider for consensus and signal-layer context; use nse_company_filings
for primary NSE announcements, actions, board meetings, results and shareholding;
use nse_equity_snapshot for live quote and security metadata; use
equity_trading_history for price, volume, volatility and delivery analysis; use
nse_market_scan for breadth, movers, activity and VIX; use equity_event_calendar
for cross-market catalyst discovery; use exchange_deals for bulk, block and
short-selling activity; use nse_derivatives_snapshot for options positioning,
max pain, PCR, lot size and F&O-ban status;
use institutional_activity for FII/DII, FPI and participant derivatives reports;
use india_market_context for Nifty total-return and MCX commodity context; use
nse_list_index for live NSE index constituents (Nifty 50, Bank Nifty, sectoral
lists, F&O universe); and use web_research for current events and external facts.
Use the chart tools when a visual summary materially helps: generate_bar_chart,
generate_horizontal_bar_chart, generate_line_chart, generate_pie_chart,
generate_stacked_bar_chart, generate_area_chart, generate_scatter_chart, and
generate_heatmap_chart. Chart inputs are caller-supplied research figures, so label
them accurately and preserve the returned artifact path in the final response when
appropriate.
Distinguish sourced facts from your analysis or uncertainty, and include source URLs
returned by tools when they materially support the answer. Never invent a source,
price, date, metric, quote, or conclusion.

For multi-step or slow research, call send_update before starting a meaningful
investigation and again when you have a useful finding, an uncertainty, or a changed
plan. Each update should be a natural multi-sentence note to the user, not a terse
status label. Do not use send_update for the final answer.

twitter_search is a scarce social-signal tool, capped per agent instance. Use it only
for the highest-value, time-sensitive X/Twitter question after considering whether
the answer is already available from grounded sources. Treat X posts as unverified
discussion unless corroborated by stronger evidence, and never call the tool again
after it reports that its budget has been exhausted.

Source-backed tools are single-flight by source: Screener tools share one slot,
signals provider tools share one slot, NSE-backed tools share one slot, web_research has its
own slot, and twitter_search has its own slot. If a tool returns status "busy", it
returned immediately because another tool from that source is still running. Wait for
that request to finish, then retry the tool yourself; do not start another tool from
the same source in the meantime.

Finish with a concise, decision-useful synthesis: key findings, important risks or
unknowns, and the evidence behind them. This is research, not personalized financial
advice; avoid telling the user to buy or sell a security.
"""

MIDAS_SYSTEM_PROMPT = f"{MIDAS_PRIMARY_SYSTEM_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}"


def build_subagents() -> list[dict[str, Any]]:
    """Build the two research roles and the publication-only report role."""
    research_model = get_research_model()
    report_runnable = create_agent(
        get_summarizer_model(),
        tools=REPORT_TOOLS,
        system_prompt=REPORT_AGENT_PROMPT,
        name="report-agent",
    )
    return [
        {
            "name": "research-agent",
            "description": (
                "Primary Indian-equity screen and deep-research analyst. Use after the "
                "mandate and complete universe artifacts exist; it writes the primary "
                "research and selection Markdown files."
            ),
            "system_prompt": f"{RESEARCH_AGENT_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}",
            "model": research_model,
            "tools": MIDAS_TOOLS,
        },
        {
            "name": "adversarial-agent",
            "description": (
                "Competing Indian-equity analyst. Invoke first for a blind independent "
                "screen and later for an evidence-based critique of the primary work."
            ),
            "system_prompt": f"{ADVERSARIAL_AGENT_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}",
            "model": research_model,
            "tools": MIDAS_TOOLS,
        },
        {
            "name": "report-agent",
            "description": (
                "Publication-only agent used after all eight Markdown artifacts pass "
                "validation. It can only compile the completed run into a PDF."
            ),
            "runnable": report_runnable,
        },
    ]


def create_midas_agent(*, checkpointer: Any | None = None):
    """Create the staged Midas lead agent with a persistent, restricted workspace."""
    workspace = Path.cwd()
    backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
    permissions = [
        FilesystemPermission(
            operations=["read"],
            paths=["/.env", "/.env.*", "/.git/**"],
            mode="deny",
        ),
        FilesystemPermission(
            operations=["write"],
            paths=["/output/research/**"],
            mode="allow",
        ),
        FilesystemPermission(
            operations=["write"],
            paths=["/**"],
            mode="deny",
        ),
    ]
    return create_deep_agent(
        model=get_main_model(),
        tools=MIDAS_TOOLS,
        system_prompt=MIDAS_SYSTEM_PROMPT,
        subagents=build_subagents(),
        backend=backend,
        permissions=permissions,
        checkpointer=checkpointer,
        name="midas-lead-analyst",
    )


class _LazyMidasAgent:
    """Keep imports cheap while preserving the historical module-level agent API."""

    _instance: Any | None = None

    def __getattr__(self, name: str) -> Any:
        if self._instance is None:
            self._instance = create_midas_agent()
        return getattr(self._instance, name)


agent = _LazyMidasAgent()

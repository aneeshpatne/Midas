from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission

from .model import (
    get_deep_research_model,
    get_main_model,
    get_research_model,
    get_summarizer_model,
)
from .prompts import (
    ADVERSARIAL_AGENT_PROMPT,
    DEEP_RESEARCH_AGENT_PROMPT,
    MIDAS_PRIMARY_SYSTEM_PROMPT,
    REPORT_AGENT_PROMPT,
    RESEARCH_AGENT_PROMPT,
)
from .reporting import REPORT_TOOLS
from .tools import MIDAS_TOOLS

MIDAS_TOOL_GUIDANCE = """Use research tools to gather evidence before factual claims.
Start with the complete universe and primary/company evidence: use nse_list_index for
live NSE constituents and methodology context; nse_company_filings for exchange
announcements, results, shareholding, governance and corporate actions; Screener for
long financial history, statements, peers and concalls; credit-rating and regulatory
evidence when available; and web_research for annual reports, official disclosures,
industry evidence, governance history and external facts.

Use signals provider consensus/signals, live quotes, trading history, market scans, event
calendars, bulk/block/short deals, derivatives positioning, institutional flows,
market context and Twitter only as supplementary valuation or monitoring context.
Upcoming results, consensus upside, broker changes, flows, technicals, price action,
positioning, catalysts and social discussion must never increase the Long-Term
Business Quality Score or displace primary evidence. Quarterly data update the
long-term record; they do not define it.

For each calculation preserve the period, formula, consolidated/standalone basis,
exceptional-item treatment and dilution treatment. Apply sector-specific metrics and
normalize cyclical or exceptional earnings before scoring.

For every serious candidate record the exact price date, time and timezone; reconcile
share count, market capitalisation, enterprise value or net cash/debt, latest reported
period and material announcements to the same analysis cut-off. Stale or materially
mismatched inputs cannot support an "at current prices" conclusion. Trace every
decisive claim through artifact source ledgers to original primary evidence.

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
for a material monitoring question that cannot be answered from grounded sources.
Treat posts as unverified discussion unless corroborated, never use popularity as
investment evidence, and never call the tool after its budget is exhausted.

Source-backed tools are single-flight by source: Screener tools share one slot,
signals provider tools share one slot, NSE-backed tools share one slot, web_research has its
own slot, and twitter_search has its own slot. If a tool returns status "busy", it
returned immediately because another tool from that source is still running. Wait for
that request to finish, then retry the tool yourself; do not start another tool from
the same source in the meantime.

Run all scraping and market-data tools sequentially, never in parallel. This includes
Screener, signals provider, NSE, trading-history, calendar, deals, derivatives,
institutional-activity, and market-context tools. Complete one such call and receive
its tool result before starting the next. Only web_research calls are exempt from
this cross-tool sequencing rule, although web_research's own source gate and any busy
response must still be respected.

Finish with a decision-useful long-horizon synthesis: separate business quality,
valuation and evidence confidence; preserve expensive quality on the watchlist;
classify missing evidence as Insufficient Evidence; identify permanent thesis risks;
and never force three final selections.
This is research, not personalized financial advice; never tell the user to buy or
sell a security.
"""

MIDAS_SYSTEM_PROMPT = f"{MIDAS_PRIMARY_SYSTEM_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}"


def build_subagents() -> list[dict[str, Any]]:
    """Build the screening, challenge, deep-dive, and report roles."""
    research_model = get_research_model()
    report_runnable = create_deep_agent(
        model=get_summarizer_model(),
        tools=REPORT_TOOLS,
        system_prompt=REPORT_AGENT_PROMPT,
        backend=FilesystemBackend(root_dir=Path.cwd(), virtual_mode=True),
        permissions=[
            FilesystemPermission(
                operations=["write"],
                paths=["/output/research/**"],
                mode="allow",
            ),
            FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
        ],
        name="report-agent",
    )
    return [
        {
            "name": "research-agent",
            "description": (
                "Primary Indian-equity screen and shortlist analyst. Use after the "
                "mandate and complete universe artifacts exist; it writes the primary "
                "research and eight-to-ten-company shortlist Markdown files."
            ),
            "system_prompt": f"{RESEARCH_AGENT_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}",
            "model": research_model,
            "tools": MIDAS_TOOLS,
        },
        {
            "name": "adversarial-agent",
            "description": (
                "Competing Indian-equity analyst. Invoke first for a blind independent "
                "screen, then for an evidence-based critique, and after equal-depth "
                "research for independent company-by-company bear cases."
            ),
            "system_prompt": f"{ADVERSARIAL_AGENT_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}",
            "model": research_model,
            "tools": MIDAS_TOOLS,
        },
        {
            "name": "deep-research-agent",
            "description": (
                "Equal-depth company deep-dive analyst. Invoke only after "
                "06_deep_dive_shortlist.md exists, for identical investment-grade "
                "diligence on all eight to ten assigned companies; it writes "
                "07_equal_depth_deep_research.md."
            ),
            "system_prompt": f"{DEEP_RESEARCH_AGENT_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}",
            "model": get_deep_research_model(),
            "tools": MIDAS_TOOLS,
        },
        {
            "name": "report-agent",
            "description": (
                "Narrative report editor used after all ten research artifacts are "
                "complete. It reads them, writes a polished report, and renders a PDF."
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

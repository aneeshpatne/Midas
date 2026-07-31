import re
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
from .modes import (
    DEEP_WIDE_ROOT_AGENT_ID,
    DEFAULT_RESEARCH_MODE,
    SINGLE_STOCK_ROOT_AGENT_ID,
    ResearchMode,
    normalize_research_mode,
)
from .prompts import (
    ADVERSARIAL_AGENT_PROMPT,
    DEEP_RESEARCH_AGENT_PROMPT,
    FOCUSED_STOCK_SYSTEM_PROMPT,
    MIDAS_PRIMARY_SYSTEM_PROMPT,
    REPORT_AGENT_PROMPT,
    RESEARCH_AGENT_PROMPT,
)
from .reporting import REPORT_TOOLS
from .tools import MIDAS_TOOLS

_AGENT_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{7,127}$")

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

For small-cap and mid-cap candidates, use available ownership, equity-snapshot and
trading-history evidence to calculate free float, median traded value/volume,
delivery, drawdown, volatility, low-volume and circuit-limit frequency, entry/exit
days, slippage and stress liquidity. Use direct market evidence for bid-ask spreads
when available. Never invent an unavailable liquidity field; classify a
decision-material gap as Insufficient Evidence.

Model the relevant sector/size TRI, broad TRI, Indian government-security benchmark
and inflation using the same analysis cut-off, horizon, scenario convention and
annualization basis as the company. Preserve source inputs and do not compare a
detailed company return model with an assumed index return.

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


def _workspace_prompt(prompt: str, *, isolated: bool) -> str:
    return prompt.replace("/output/research", "/research") if isolated else prompt


def build_subagents(
    *, workspace: Path | None = None, isolated: bool = False
) -> list[dict[str, Any]]:
    """Build the screening, challenge, deep-dive, and report roles."""
    workspace = (workspace or Path.cwd()).resolve()
    research_model = get_research_model()
    report_runnable = create_deep_agent(
        model=get_summarizer_model(),
        tools=REPORT_TOOLS,
        system_prompt=_workspace_prompt(REPORT_AGENT_PROMPT, isolated=isolated),
        backend=FilesystemBackend(root_dir=workspace, virtual_mode=True),
        permissions=[
            FilesystemPermission(
                operations=["read", "write"],
                paths=["/**"],
                mode="allow",
            ),
        ],
        name="report-agent",
    )
    return [
        {
            "name": "research-agent",
            "description": (
                "Primary Indian-equity screen and shortlist analyst. Use after the "
                "mandate and complete universe artifacts exist; it writes the primary "
                "research and an evidence-determined equal-depth candidate set."
            ),
            "system_prompt": _workspace_prompt(
                f"{RESEARCH_AGENT_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}",
                isolated=isolated,
            ),
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
            "system_prompt": _workspace_prompt(
                f"{ADVERSARIAL_AGENT_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}",
                isolated=isolated,
            ),
            "model": research_model,
            "tools": MIDAS_TOOLS,
        },
        {
            "name": "deep-research-agent",
            "description": (
                "Equal-depth company deep-dive analyst. Invoke only after "
                "06_deep_dive_shortlist.md exists, for identical investment-grade "
                "diligence on every assigned evidence-qualified company; it writes "
                "07_equal_depth_deep_research.md."
            ),
            "system_prompt": _workspace_prompt(
                f"{DEEP_RESEARCH_AGENT_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}",
                isolated=isolated,
            ),
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


def _agent_environment(
    *, agent_id: str | None, workspace: Path | None
) -> tuple[Path, FilesystemBackend, list[FilesystemPermission]]:
    project_workspace = (workspace or Path.cwd()).resolve()
    if agent_id is None:
        agent_workspace = project_workspace
    else:
        if not _AGENT_ID.fullmatch(agent_id):
            raise ValueError("agent_id must contain only letters, numbers, hyphens, or underscores")
        output_root = (project_workspace / "output").resolve()
        agent_workspace = (output_root / agent_id).resolve()
        agent_workspace.relative_to(output_root)
        agent_workspace.mkdir(parents=True, exist_ok=True)
    backend = FilesystemBackend(root_dir=agent_workspace, virtual_mode=True)
    permissions = [
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/**"],
            mode="allow",
        ),
    ]
    return agent_workspace, backend, permissions


def create_midas_agent(
    *,
    checkpointer: Any | None = None,
    agent_id: str | None = None,
    workspace: Path | None = None,
):
    """Create the staged Deep Wide Research Agent."""
    agent_workspace, backend, permissions = _agent_environment(
        agent_id=agent_id,
        workspace=workspace,
    )
    return create_deep_agent(
        model=get_main_model(),
        tools=MIDAS_TOOLS,
        system_prompt=_workspace_prompt(MIDAS_SYSTEM_PROMPT, isolated=agent_id is not None),
        subagents=build_subagents(
            workspace=agent_workspace,
            isolated=agent_id is not None,
        ),
        backend=backend,
        permissions=permissions,
        checkpointer=checkpointer,
        name=DEEP_WIDE_ROOT_AGENT_ID,
    )


def create_single_stock_agent(
    *,
    checkpointer: Any | None = None,
    agent_id: str | None = None,
    workspace: Path | None = None,
):
    """Create the narrow, investment-grade Single Stock Research Agent."""
    _, backend, permissions = _agent_environment(
        agent_id=agent_id,
        workspace=workspace,
    )
    return create_deep_agent(
        model=get_deep_research_model(),
        tools=MIDAS_TOOLS,
        system_prompt=_workspace_prompt(
            f"{FOCUSED_STOCK_SYSTEM_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}",
            isolated=agent_id is not None,
        ),
        backend=backend,
        permissions=permissions,
        checkpointer=checkpointer,
        name=SINGLE_STOCK_ROOT_AGENT_ID,
    )


def create_research_agent(
    mode: ResearchMode = DEFAULT_RESEARCH_MODE,
    *,
    checkpointer: Any | None = None,
    agent_id: str | None = None,
    workspace: Path | None = None,
):
    """Create the top-level graph for a selected research mode."""
    factory = (
        create_single_stock_agent
        if normalize_research_mode(mode) == ResearchMode.SINGLE_STOCK
        else create_midas_agent
    )
    return factory(
        checkpointer=checkpointer,
        agent_id=agent_id,
        workspace=workspace,
    )


class _LazyMidasAgent:
    """Keep imports cheap while preserving the historical module-level agent API."""

    _instance: Any | None = None

    def __getattr__(self, name: str) -> Any:
        if self._instance is None:
            self._instance = create_midas_agent()
        return getattr(self._instance, name)


agent = _LazyMidasAgent()

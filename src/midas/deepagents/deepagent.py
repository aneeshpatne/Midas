import re
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission

from .db_tools import ensure_midas_db
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
from .tools import MIDAS_TOOLS

_AGENT_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{7,127}$")

MIDAS_TOOL_GUIDANCE = """Use research tools to gather evidence before factual claims.
Start with the complete universe and primary/company evidence: use nse_list_index for
live NSE constituents and methodology context; nse_company_filings for exchange
announcements, results, shareholding, governance and corporate actions; company_fundamentals for
long financial history, statements, peers and concalls; credit-rating and regulatory
evidence when available; and web_research for annual reports, official disclosures,
industry evidence, governance history and external facts.

Use market_signals, live quotes, trading history, market scans, event
calendars, bulk/block/short deals, derivatives positioning, institutional flows,
market context and Twitter only as supplementary valuation or monitoring context.
Upcoming results, consensus upside, broker changes, flows, technicals, price action,
positioning, catalysts and social discussion must never increase the Long-Term
Business Quality Score or displace primary evidence. Quarterly data update the
long-term record; they do not define it.

## Midas DB (durable store — required for every run)

All research durability lives in Midas DB (same tools as midas-db-mcp). Do **not**
create filesystem research folders or final PDF/HTML/Markdown report files.

Required DB tools:
- research_run_create — start one isolated run; keep the returned `id` for the whole job
- research_run_set_mandate — freeze scope/horizon/cut-off
- research_security_add — names under study (SUBJECT/PEER/BENCHMARK/…)
- research_evidence_append — append-only stage results, sources, calcs, decisions
  (use record_type values such as mandate, universe, primary_screen, shortlist,
  adversary_independent, adversary_critique, deep_dive_shortlist, equal_depth,
  finalist_bear, ic_decision, source, calculation)
- research_run_get_bundle / research_evidence_list — read prior stage work by run id
- research_run_set_report + research_run_complete — store the final A–J decision text
  in DB only

Optional master data / paper portfolio:
- company_create / security_create / security_get_by_ticker when resolving listings
- portfolio_*, investment_case_*, thesis_revision_*, transaction_*, market_price_*
  only when the user asks for paper-portfolio actions; research_link_portfolio only
  after a finished run when admitting a name into a portfolio

Check every DB/market tool JSON for ``ok`` before trusting the payload.

For each calculation preserve the period, formula, consolidated/standalone basis,
exceptional-item treatment and dilution treatment. Apply sector-specific metrics and
normalize cyclical or exceptional earnings before scoring.

For every serious candidate record the exact price date, time and timezone; reconcile
share count, market capitalisation, enterprise value or net cash/debt, latest reported
period and material announcements to the same analysis cut-off. Stale or materially
mismatched inputs cannot support an "at current prices" conclusion. Trace every
decisive claim through research_evidence source rows to original primary evidence.

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
them accurately. Charts are optional aids only — never the durable research record.
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

Source-backed tools are single-flight by source: fundamentals tools share one slot,
signals tools share one slot, NSE-backed tools share one slot, web_research has its
own slot, and twitter_search has its own slot. If a tool returns status "busy", it
returned immediately because another tool from that source is still running. Wait for
that request to finish, then retry the tool yourself; do not start another tool from
the same source in the meantime.

Run all scraping and market-data tools sequentially, never in parallel. This includes
company_fundamentals, market_signals, NSE, trading-history, calendar, deals, derivatives,
institutional-activity, and market-context tools. Complete one such call and receive
its tool result before starting the next. Only web_research calls are exempt from
this cross-tool sequencing rule, although web_research's own source gate and any busy
response must still be respected. Midas DB tools may run freely between market calls.

Finish with a decision-useful long-horizon synthesis in chat **and** a completed
research run in Midas DB (report stored via research_run_set_report /
research_run_complete). Separate business quality, valuation and evidence confidence;
preserve expensive quality on the watchlist; classify missing evidence as Insufficient
Evidence; identify permanent thesis risks; never force three final selections.
Do not produce final PDF, HTML, or filesystem Markdown report files.
This is research, not personalized financial advice; never tell the user to buy or
sell a security.
"""

MIDAS_SYSTEM_PROMPT = f"{MIDAS_PRIMARY_SYSTEM_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}"


def build_subagents(
    *, workspace: Path | None = None, isolated: bool = False
) -> list[dict[str, Any]]:
    """Build the screening, challenge, deep-dive, and report roles."""
    del workspace, isolated  # filesystem isolation no longer drives research records
    research_model = get_research_model()
    report_runnable = create_deep_agent(
        model=get_summarizer_model(),
        tools=MIDAS_TOOLS,
        system_prompt=f"{REPORT_AGENT_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}",
        name="report-agent",
    )
    return [
        {
            "name": "research-agent",
            "description": (
                "Primary Indian-equity screen and shortlist analyst. Use after the "
                "mandate and universe evidence exist on the research run; it appends "
                "primary screen and shortlist records to Midas DB."
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
                "research for independent company-by-company bear cases. Writes only "
                "to the active research_run_id evidence ledger."
            ),
            "system_prompt": f"{ADVERSARIAL_AGENT_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}",
            "model": research_model,
            "tools": MIDAS_TOOLS,
        },
        {
            "name": "deep-research-agent",
            "description": (
                "Equal-depth company deep-dive analyst. Invoke only after the deep-dive "
                "shortlist evidence exists for the active research_run_id; appends "
                "equal-depth diligence records for every assigned company."
            ),
            "system_prompt": f"{DEEP_RESEARCH_AGENT_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}",
            "model": get_deep_research_model(),
            "tools": MIDAS_TOOLS,
        },
        {
            "name": "report-agent",
            "description": (
                "Narrative report editor used after staged research evidence is complete. "
                "Reads the research run bundle from Midas DB, writes the A–J decision "
                "report into research_runs.report_md, and completes the run. No PDF."
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
    ensure_midas_db()
    agent_workspace, backend, permissions = _agent_environment(
        agent_id=agent_id,
        workspace=workspace,
    )
    return create_deep_agent(
        model=get_main_model(),
        tools=MIDAS_TOOLS,
        system_prompt=MIDAS_SYSTEM_PROMPT,
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
    ensure_midas_db()
    _, backend, permissions = _agent_environment(
        agent_id=agent_id,
        workspace=workspace,
    )
    return create_deep_agent(
        model=get_deep_research_model(),
        tools=MIDAS_TOOLS,
        system_prompt=f"{FOCUSED_STOCK_SYSTEM_PROMPT}\n\n{MIDAS_TOOL_GUIDANCE}",
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

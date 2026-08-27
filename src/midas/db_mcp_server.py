"""Standalone MCP server for Midas DB (portfolios, securities, research runs).

Exposes paper-portfolio and research-run tools over the Model Context Protocol
so hosts such as Codex, Claude Desktop, or Cursor can manage Midas DB without
running the full research agent.

Run with stdio (default)::

    uv run midas-db-mcp
    # or: python -m midas.db_mcp_server

Optional::

    MIDAS_DB_PATH=/path/to/midas.db

Codex ``~/.codex/config.toml`` example::

    [mcp_servers.midas-db]
    command = "uv"
    args = ["run", "--directory", "/absolute/path/to/Midas", "midas-db-mcp"]
    tool_timeout_sec = 60
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from midas.db.connection import configure, get_db_path
from midas.db.errors import MidasDbError
from midas.db.helpers import now_ms
from midas.db.migrate import run_migrations
from midas.mcp_sanitize import sanitize_for_mcp, scrub_text
from midas.db.models import (
    AddResearchRunSecurityInput,
    AppendResearchEvidenceInput,
    CreateCompanyInput,
    CreateInvestmentCaseInput,
    CreatePortfolioAccountInput,
    CreatePortfolioInput,
    CreateResearchPortfolioLinkInput,
    CreateResearchRunInput,
    CreateSecurityInput,
    CreateThesisRevisionInput,
    CreateTradeProposalInput,
    CreateTransactionInput,
    ProposedTrade,
    UpdateCompanyInput,
    UpdateInvestmentCaseInput,
    UpdatePortfolioAccountInput,
    UpdatePortfolioInput,
    UpdateResearchRunInput,
    UpdateSecurityInput,
    UpsertMarketPriceInput,
)
from midas.db.services import (
    companies_service,
    investment_cases_service,
    market_prices_service,
    portfolio_accounts_service,
    portfolios_service,
    research_runs_service,
    securities_service,
    thesis_revisions_service,
    trade_proposals_service,
    transactions_service,
)

_SERVER_INSTRUCTIONS = """\
Midas DB tools for paper portfolios, securities master, investment cases,
thesis revisions, cash/trade ledger, approval-gated trade proposals, market
prices, and DB-backed equity research runs.

All tools return compact JSON with an ``ok`` field. Check ``ok`` before trusting
the payload. Money amounts are integer paise (₹1 = 100 paise). Share quantities
are integer micros (1 share = 1_000_000 micros). Timestamps are epoch ms.

Prefer:
- company_create / security_create for master data
- portfolio_create + account_create + deposit (transaction_create DEPOSIT)
- investment_case_create + thesis_revision_create for thesis work
- trade_proposal_create → user approval of ID → trade_proposal_approve →
  trade_proposal_execute for BUY/SELL (never transaction_create for trades)
- research_run_create / research_evidence_append for diligence ledgers
- research_link_portfolio only after a run is finished when admitting names

Portfolio actions are paper only — not broker instructions.
"""


def _dump(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_dump(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _dump(v) for k, v in obj.items()}
    return obj


def _ok(data: Any) -> str:
    # Scrub URL fields/strings before they leave the MCP process.
    return json.dumps(
        {"ok": True, "data": sanitize_for_mcp(_dump(data))},
        indent=2,
        default=str,
    )


def _fail(error: BaseException) -> str:
    name = type(error).__name__
    return json.dumps(
        {
            "ok": False,
            "error": {"name": name, "message": scrub_text(str(error))},
        },
        indent=2,
    )


def _run(fn: Any) -> str:
    try:
        return _ok(fn())
    except MidasDbError as exc:
        return _fail(exc)
    except Exception as exc:  # noqa: BLE001 — surface unexpected errors to MCP hosts
        logging.exception("midas-db tool failed")
        return _fail(exc)


def create_db_mcp_server() -> FastMCP:
    """Build FastMCP server with Midas DB tools."""
    server = FastMCP("midas-db", instructions=_SERVER_INSTRUCTIONS)

    # --- Companies ---
    @server.tool()
    def company_create(
        name: str,
        legal_name: str | None = None,
        sector: str | None = None,
        industry: str | None = None,
        market_cap_bucket: Literal["LARGE", "MID", "SMALL", "MICRO", "OTHER"]
        | None = None,
        country_code: str = "IN",
        website: str | None = None,
        classification_source: str | None = None,
        classification_as_of: str | None = None,
        notes: str | None = None,
        id: str | None = None,
    ) -> str:
        """Create issuer metadata (optional parent of listings)."""
        return _run(
            lambda: companies_service.create(
                CreateCompanyInput(
                    id=id,
                    name=name,
                    legal_name=legal_name,
                    sector=sector,
                    industry=industry,
                    market_cap_bucket=market_cap_bucket,
                    country_code=country_code,
                    website=website,
                    classification_source=classification_source,
                    classification_as_of=classification_as_of,
                    notes=notes,
                )
            )
        )

    @server.tool()
    def company_get(id: str) -> str:
        """Get a company by id."""
        return _run(lambda: companies_service.get_by_id(id))

    @server.tool()
    def company_list(
        sector: str | None = None,
        industry: str | None = None,
        market_cap_bucket: Literal["LARGE", "MID", "SMALL", "MICRO", "OTHER"]
        | None = None,
        limit: int = 500,
    ) -> str:
        """List companies with optional sector/industry/bucket filters."""
        return _run(
            lambda: companies_service.list(
                sector=sector,
                industry=industry,
                market_cap_bucket=market_cap_bucket,
                limit=limit,
            )
        )

    @server.tool()
    def company_update(
        id: str,
        name: str | None = None,
        legal_name: str | None = None,
        sector: str | None = None,
        industry: str | None = None,
        market_cap_bucket: Literal["LARGE", "MID", "SMALL", "MICRO", "OTHER"]
        | None = None,
        country_code: str | None = None,
        website: str | None = None,
        classification_source: str | None = None,
        classification_as_of: str | None = None,
        notes: str | None = None,
    ) -> str:
        """Update company metadata. Omitted fields are left unchanged."""
        patch: dict[str, Any] = {}
        for key, val in {
            "name": name,
            "legal_name": legal_name,
            "sector": sector,
            "industry": industry,
            "market_cap_bucket": market_cap_bucket,
            "country_code": country_code,
            "website": website,
            "classification_source": classification_source,
            "classification_as_of": classification_as_of,
            "notes": notes,
        }.items():
            if val is not None:
                patch[key] = val
        return _run(
            lambda: companies_service.update(id, UpdateCompanyInput(**patch))
        )

    @server.tool()
    def company_stats() -> str:
        """Company counts by sector, industry, and market-cap bucket."""
        return _run(companies_service.stats)

    @server.tool()
    def company_list_securities(company_id: str) -> str:
        """List securities linked to a company."""
        return _run(lambda: companies_service.list_securities(company_id))

    # --- Securities ---
    @server.tool()
    def security_create(
        ticker: str,
        exchange: str,
        name: str,
        currency: str = "INR",
        security_type: Literal[
            "EQUITY", "ETF", "MUTUAL_FUND", "BOND", "REIT", "CRYPTO", "OTHER"
        ] = "EQUITY",
        company_id: str | None = None,
        isin: str | None = None,
        is_active: bool = True,
        id: str | None = None,
    ) -> str:
        """Create a tradable listing (exchange+ticker unique)."""
        return _run(
            lambda: securities_service.create(
                CreateSecurityInput(
                    id=id,
                    company_id=company_id,
                    ticker=ticker,
                    exchange=exchange,
                    name=name,
                    security_type=security_type,
                    currency=currency,
                    isin=isin,
                    is_active=is_active,
                )
            )
        )

    @server.tool()
    def security_get(id: str, with_company: bool = True) -> str:
        """Get a security by id (optionally with company metadata)."""
        if with_company:
            return _run(lambda: securities_service.get_by_id_with_company(id))
        return _run(lambda: securities_service.get_by_id(id))

    @server.tool()
    def security_get_by_ticker(exchange: str, ticker: str) -> str:
        """Lookup security by exchange + ticker."""
        return _run(
            lambda: securities_service.get_by_exchange_ticker(exchange, ticker)
        )

    @server.tool()
    def security_list(
        active_only: bool = False,
        company_id: str | None = None,
        with_company: bool = False,
    ) -> str:
        """List securities."""
        if with_company:
            return _run(
                lambda: securities_service.list_with_company(
                    active_only=active_only, company_id=company_id
                )
            )
        return _run(
            lambda: securities_service.list(
                active_only=active_only, company_id=company_id
            )
        )

    @server.tool()
    def security_update(
        id: str,
        company_id: str | None = None,
        ticker: str | None = None,
        exchange: str | None = None,
        name: str | None = None,
        security_type: Literal[
            "EQUITY", "ETF", "MUTUAL_FUND", "BOND", "REIT", "CRYPTO", "OTHER"
        ]
        | None = None,
        currency: str | None = None,
        isin: str | None = None,
        is_active: bool | None = None,
        clear_company: bool = False,
    ) -> str:
        """Update a security. Set clear_company=true to unlink company_id."""
        patch: dict[str, Any] = {}
        if clear_company:
            patch["company_id"] = None
        elif company_id is not None:
            patch["company_id"] = company_id
        for key, val in {
            "ticker": ticker,
            "exchange": exchange,
            "name": name,
            "security_type": security_type,
            "currency": currency,
            "isin": isin,
            "is_active": is_active,
        }.items():
            if val is not None:
                patch[key] = val
        return _run(
            lambda: securities_service.update(id, UpdateSecurityInput(**patch))
        )

    @server.tool()
    def security_link_company(
        security_id: str, company_id: str | None = None
    ) -> str:
        """Link or unlink a security to a company (company_id null unlinks)."""
        return _run(
            lambda: securities_service.link_company(security_id, company_id)
        )

    # --- Portfolios ---
    @server.tool()
    def portfolio_create(
        name: str,
        description: str | None = None,
        strategy: str | None = None,
        base_currency: str = "INR",
        target_capital_paise: int | None = None,
        id: str | None = None,
    ) -> str:
        """Create a paper portfolio. target_capital_paise is planned budget only."""
        return _run(
            lambda: portfolios_service.create(
                CreatePortfolioInput(
                    id=id,
                    name=name,
                    description=description,
                    strategy=strategy,
                    base_currency=base_currency,
                    target_capital_paise=target_capital_paise,
                )
            )
        )

    @server.tool()
    def portfolio_get(id: str) -> str:
        """Get a portfolio by id."""
        return _run(lambda: portfolios_service.get_by_id(id))

    @server.tool()
    def portfolio_list(include_archived: bool = False) -> str:
        """List portfolios (archived excluded by default)."""
        return _run(
            lambda: portfolios_service.list(include_archived=include_archived)
        )

    @server.tool()
    def portfolio_update(
        id: str,
        name: str | None = None,
        description: str | None = None,
        strategy: str | None = None,
        base_currency: str | None = None,
        target_capital_paise: int | None = None,
    ) -> str:
        """Update portfolio metadata or planned target capital."""
        patch: dict[str, Any] = {}
        for key, val in {
            "name": name,
            "description": description,
            "strategy": strategy,
            "base_currency": base_currency,
            "target_capital_paise": target_capital_paise,
        }.items():
            if val is not None:
                patch[key] = val
        return _run(
            lambda: portfolios_service.update(id, UpdatePortfolioInput(**patch))
        )

    @server.tool()
    def portfolio_archive(id: str) -> str:
        """Soft-archive a portfolio."""
        return _run(lambda: portfolios_service.archive(id))

    @server.tool()
    def portfolio_unarchive(id: str) -> str:
        """Restore an archived portfolio."""
        return _run(lambda: portfolios_service.unarchive(id))

    @server.tool()
    def portfolio_cash_summary(portfolio_id: str) -> str:
        """Cash/funding snapshot from the transaction ledger."""
        return _run(lambda: portfolios_service.get_cash_summary(portfolio_id))

    @server.tool()
    def portfolio_delete(id: str) -> str:
        """Hard-delete a portfolio and cascade-related rows. Prefer archive."""
        return _run(
            lambda: (
                portfolios_service.delete(id),
                {"deleted": True, "id": id},
            )[1]
        )

    # --- Accounts ---
    @server.tool()
    def account_create(
        portfolio_id: str,
        name: str,
        institution: str | None = None,
        account_reference: str | None = None,
        currency: str = "INR",
        id: str | None = None,
    ) -> str:
        """Create a broker/custody sleeve inside a portfolio."""
        return _run(
            lambda: portfolio_accounts_service.create(
                CreatePortfolioAccountInput(
                    id=id,
                    portfolio_id=portfolio_id,
                    name=name,
                    institution=institution,
                    account_reference=account_reference,
                    currency=currency,
                )
            )
        )

    @server.tool()
    def account_list(portfolio_id: str) -> str:
        """List accounts for a portfolio."""
        return _run(
            lambda: portfolio_accounts_service.list_by_portfolio(portfolio_id)
        )

    @server.tool()
    def account_get(id: str) -> str:
        """Get a portfolio account by id."""
        return _run(lambda: portfolio_accounts_service.get_by_id(id))

    @server.tool()
    def account_update(
        id: str,
        name: str | None = None,
        institution: str | None = None,
        account_reference: str | None = None,
        currency: str | None = None,
    ) -> str:
        """Update portfolio account metadata."""
        patch: dict[str, Any] = {}
        for key, val in {
            "name": name,
            "institution": institution,
            "account_reference": account_reference,
            "currency": currency,
        }.items():
            if val is not None:
                patch[key] = val
        return _run(
            lambda: portfolio_accounts_service.update(
                id, UpdatePortfolioAccountInput(**patch)
            )
        )

    # --- Investment cases ---
    @server.tool()
    def investment_case_create(
        portfolio_id: str,
        security_id: str,
        name: str,
        status: Literal[
            "WATCHLIST", "ACTIVE", "REDUCING", "EXITED", "INVALIDATED", "ARCHIVED"
        ] = "WATCHLIST",
        conviction: int | None = None,
        time_horizon_months: int | None = None,
        opened_at: int | None = None,
        closed_at: int | None = None,
        id: str | None = None,
    ) -> str:
        """Create a thesis-backed position intent for a name in a portfolio."""
        return _run(
            lambda: investment_cases_service.create(
                CreateInvestmentCaseInput(
                    id=id,
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    name=name,
                    status=status,
                    conviction=conviction,  # type: ignore[arg-type]
                    time_horizon_months=time_horizon_months,
                    opened_at=opened_at,
                    closed_at=closed_at,
                )
            )
        )

    @server.tool()
    def investment_case_get(id: str) -> str:
        """Get an investment case by id."""
        return _run(lambda: investment_cases_service.get_by_id(id))

    @server.tool()
    def investment_case_list(
        portfolio_id: str,
        status: Literal[
            "WATCHLIST", "ACTIVE", "REDUCING", "EXITED", "INVALIDATED", "ARCHIVED"
        ]
        | None = None,
    ) -> str:
        """List investment cases for a portfolio."""
        return _run(
            lambda: investment_cases_service.list_by_portfolio(
                portfolio_id, status=status
            )
        )

    @server.tool()
    def investment_case_update(
        id: str,
        name: str | None = None,
        status: Literal[
            "WATCHLIST", "ACTIVE", "REDUCING", "EXITED", "INVALIDATED", "ARCHIVED"
        ]
        | None = None,
        conviction: int | None = None,
        time_horizon_months: int | None = None,
        opened_at: int | None = None,
        closed_at: int | None = None,
    ) -> str:
        """Update investment case fields."""
        patch: dict[str, Any] = {}
        for key, val in {
            "name": name,
            "status": status,
            "conviction": conviction,
            "time_horizon_months": time_horizon_months,
            "opened_at": opened_at,
            "closed_at": closed_at,
        }.items():
            if val is not None:
                patch[key] = val
        return _run(
            lambda: investment_cases_service.update(
                id, UpdateInvestmentCaseInput(**patch)
            )
        )

    # --- Thesis ---
    @server.tool()
    def thesis_revision_create(
        investment_case_id: str,
        thesis: str,
        revision_type: Literal[
            "INITIAL",
            "UPDATE",
            "EARNINGS_UPDATE",
            "RISK_UPDATE",
            "INVALIDATION",
            "EXIT_NOTE",
        ] = "UPDATE",
        bull_case: str | None = None,
        base_case: str | None = None,
        bear_case: str | None = None,
        catalysts: str | None = None,
        risks: str | None = None,
        invalidation_conditions: str | None = None,
        target_price_paise: int | None = None,
        conviction: int | None = None,
        effective_at: int | None = None,
        id: str | None = None,
    ) -> str:
        """Append a thesis revision (auto-increments revision_number)."""
        return _run(
            lambda: thesis_revisions_service.create(
                CreateThesisRevisionInput(
                    id=id,
                    investment_case_id=investment_case_id,
                    revision_type=revision_type,
                    thesis=thesis,
                    bull_case=bull_case,
                    base_case=base_case,
                    bear_case=bear_case,
                    catalysts=catalysts,
                    risks=risks,
                    invalidation_conditions=invalidation_conditions,
                    target_price_paise=target_price_paise,
                    conviction=conviction,  # type: ignore[arg-type]
                    effective_at=effective_at,
                )
            )
        )

    @server.tool()
    def thesis_revision_list(investment_case_id: str) -> str:
        """List thesis revisions for a case (newest first)."""
        return _run(
            lambda: thesis_revisions_service.list_by_case(investment_case_id)
        )

    @server.tool()
    def thesis_revision_get(id: str) -> str:
        """Get a thesis revision by id."""
        return _run(lambda: thesis_revisions_service.get_by_id(id))

    @server.tool()
    def thesis_revision_get_latest(investment_case_id: str) -> str:
        """Get the latest thesis revision for an investment case (or null)."""
        return _run(lambda: thesis_revisions_service.get_latest(investment_case_id))

    @server.tool()
    def thesis_revision_delete(id: str) -> str:
        """Delete a thesis revision by id."""
        return _run(
            lambda: (
                thesis_revisions_service.delete(id),
                {"deleted": True, "id": id},
            )[1]
        )

    # --- Transactions ---
    @server.tool()
    def transaction_create(
        portfolio_id: str,
        type: Literal[
            "BUY",
            "SELL",
            "DIVIDEND",
            "INTEREST",
            "FEE",
            "TAX",
            "DEPOSIT",
            "WITHDRAWAL",
            "SPLIT",
            "BONUS",
            "TRANSFER_IN",
            "TRANSFER_OUT",
        ],
        executed_at: int | None = None,
        account_id: str | None = None,
        security_id: str | None = None,
        investment_case_id: str | None = None,
        quantity_micros: int | None = None,
        price_paise: int | None = None,
        gross_amount_paise: int | None = None,
        fees_paise: int = 0,
        taxes_paise: int = 0,
        net_amount_paise: int | None = None,
        cash_effect_paise: int | None = None,
        currency: str = "INR",
        exchange_rate_micros: int = 1_000_000,
        settlement_date: str | None = None,
        external_reference: str | None = None,
        notes: str | None = None,
        id: str | None = None,
    ) -> str:
        """Record a cash or non-trade ledger event. BUY/SELL require trade_proposal_execute."""
        return _run(
            lambda: transactions_service.create(
                CreateTransactionInput(
                    id=id,
                    portfolio_id=portfolio_id,
                    account_id=account_id,
                    security_id=security_id,
                    investment_case_id=investment_case_id,
                    type=type,
                    quantity_micros=quantity_micros,
                    price_paise=price_paise,
                    gross_amount_paise=gross_amount_paise,
                    fees_paise=fees_paise,
                    taxes_paise=taxes_paise,
                    net_amount_paise=net_amount_paise,
                    cash_effect_paise=cash_effect_paise,
                    currency=currency,
                    exchange_rate_micros=exchange_rate_micros,
                    executed_at=executed_at if executed_at is not None else now_ms(),
                    settlement_date=settlement_date,
                    external_reference=external_reference,
                    notes=notes,
                )
            )
        )

    @server.tool()
    def transaction_get(id: str) -> str:
        """Get a transaction by id."""
        return _run(lambda: transactions_service.get_by_id(id))

    @server.tool()
    def transaction_list(
        portfolio_id: str,
        type: Literal[
            "BUY",
            "SELL",
            "DIVIDEND",
            "INTEREST",
            "FEE",
            "TAX",
            "DEPOSIT",
            "WITHDRAWAL",
            "SPLIT",
            "BONUS",
            "TRANSFER_IN",
            "TRANSFER_OUT",
        ]
        | None = None,
        security_id: str | None = None,
        investment_case_id: str | None = None,
        account_id: str | None = None,
        from_executed_at: int | None = None,
        to_executed_at: int | None = None,
    ) -> str:
        """List portfolio transactions (newest first)."""
        return _run(
            lambda: transactions_service.list_by_portfolio(
                portfolio_id,
                type_=type,
                security_id=security_id,
                investment_case_id=investment_case_id,
                account_id=account_id,
                from_executed_at=from_executed_at,
                to_executed_at=to_executed_at,
            )
        )

    @server.tool()
    def transaction_delete(id: str) -> str:
        """Delete a transaction (use carefully; ledger is source of truth)."""
        return _run(
            lambda: (
                transactions_service.delete(id),
                {"deleted": True, "id": id},
            )[1]
        )

    # --- Market prices ---
    @server.tool()
    def market_price_upsert(
        security_id: str,
        price_date: str,
        price_paise: int,
        currency: str = "INR",
        source: str | None = None,
        captured_at: int | None = None,
    ) -> str:
        """Upsert a daily close / mark-to-market price (YYYY-MM-DD)."""
        return _run(
            lambda: market_prices_service.upsert(
                UpsertMarketPriceInput(
                    security_id=security_id,
                    price_date=price_date,
                    price_paise=price_paise,
                    currency=currency,
                    source=source,
                    captured_at=captured_at,
                )
            )
        )

    @server.tool()
    def market_price_latest(security_id: str) -> str:
        """Get the latest stored price for a security."""
        return _run(lambda: market_prices_service.latest(security_id))

    @server.tool()
    def market_price_list(security_id: str, limit: int = 100) -> str:
        """List stored prices for a security (newest first)."""
        return _run(
            lambda: market_prices_service.list_by_security(
                security_id, limit=limit
            )
        )

    # --- Research runs ---
    @server.tool()
    def research_run_create(
        slug: str,
        workflow: Literal["single_stock", "named_comparison", "broad_universe"],
        universe_or_company: str,
        horizon_text: str,
        horizon_months: int | None = None,
        title: str | None = None,
        cutoff_at: int | None = None,
        mandate_md: str | None = None,
        primary_runtime: str | None = None,
        execution_mode: str | None = None,
        status: Literal[
            "DRAFT", "IN_PROGRESS", "COMPLETED", "BLOCKED", "ABANDONED"
        ] = "IN_PROGRESS",
        run_key: str | None = None,
        id: str | None = None,
    ) -> str:
        """Create an isolated equity-research run in Midas DB."""
        return _run(
            lambda: research_runs_service.create(
                CreateResearchRunInput(
                    id=id,
                    slug=slug,
                    run_key=run_key,
                    workflow=workflow,
                    status=status,
                    title=title,
                    universe_or_company=universe_or_company,
                    horizon_text=horizon_text,
                    horizon_months=horizon_months,
                    cutoff_at=cutoff_at,
                    mandate_md=mandate_md,
                    primary_runtime=primary_runtime,
                    execution_mode=execution_mode,
                )
            )
        )

    @server.tool()
    def research_run_get(id: str) -> str:
        """Get a research run by id (metadata only)."""
        return _run(lambda: research_runs_service.get_by_id(id))

    @server.tool()
    def research_run_get_bundle(id: str) -> str:
        """Get a research run with securities, evidence, and portfolio links."""
        return _run(lambda: research_runs_service.get_bundle(id))

    @server.tool()
    def research_run_list(
        slug: str | None = None,
        status: Literal[
            "DRAFT", "IN_PROGRESS", "COMPLETED", "BLOCKED", "ABANDONED"
        ]
        | None = None,
        workflow: Literal["single_stock", "named_comparison", "broad_universe"]
        | None = None,
        limit: int = 100,
    ) -> str:
        """List research runs (newest first)."""
        return _run(
            lambda: research_runs_service.list(
                slug=slug, status=status, workflow=workflow, limit=limit
            )
        )

    @server.tool()
    def research_run_update(
        id: str,
        title: str | None = None,
        universe_or_company: str | None = None,
        horizon_text: str | None = None,
        horizon_months: int | None = None,
        cutoff_at: int | None = None,
        mandate_md: str | None = None,
        report_md: str | None = None,
        primary_runtime: str | None = None,
        execution_mode: str | None = None,
        status: Literal[
            "DRAFT", "IN_PROGRESS", "COMPLETED", "BLOCKED", "ABANDONED"
        ]
        | None = None,
    ) -> str:
        """Update research run fields or status."""
        patch: dict[str, Any] = {}
        for key, val in {
            "title": title,
            "universe_or_company": universe_or_company,
            "horizon_text": horizon_text,
            "horizon_months": horizon_months,
            "cutoff_at": cutoff_at,
            "mandate_md": mandate_md,
            "report_md": report_md,
            "primary_runtime": primary_runtime,
            "execution_mode": execution_mode,
            "status": status,
        }.items():
            if val is not None:
                patch[key] = val
        return _run(
            lambda: research_runs_service.update(
                id, UpdateResearchRunInput(**patch)
            )
        )

    @server.tool()
    def research_run_set_mandate(id: str, mandate_md: str) -> str:
        """Write/replace the DB-backed mandate text."""
        return _run(lambda: research_runs_service.set_mandate(id, mandate_md))

    @server.tool()
    def research_run_set_report(id: str, report_md: str) -> str:
        """Write/replace the DB-backed IC report text."""
        return _run(lambda: research_runs_service.set_report(id, report_md))

    @server.tool()
    def research_run_complete(id: str, report_md: str | None = None) -> str:
        """Mark a research run COMPLETED (requires mandate; report required)."""
        return _run(lambda: research_runs_service.complete(id, report_md))

    @server.tool()
    def research_run_set_status(
        id: str,
        status: Literal[
            "DRAFT", "IN_PROGRESS", "COMPLETED", "BLOCKED", "ABANDONED"
        ],
    ) -> str:
        """Set research run status."""
        return _run(lambda: research_runs_service.set_status(id, status))

    @server.tool()
    def research_security_add(
        research_run_id: str,
        symbol: str,
        exchange: str | None = None,
        security_id: str | None = None,
        role: Literal[
            "SUBJECT", "PEER", "BENCHMARK", "NEAR_MISS", "EXCLUDED"
        ] = "SUBJECT",
        sort_order: int = 0,
        notes: str | None = None,
        id: str | None = None,
    ) -> str:
        """Add a name under study to a research run."""
        return _run(
            lambda: research_runs_service.add_security(
                AddResearchRunSecurityInput(
                    id=id,
                    research_run_id=research_run_id,
                    security_id=security_id,
                    symbol=symbol,
                    exchange=exchange,
                    role=role,
                    sort_order=sort_order,
                    notes=notes,
                )
            )
        )

    @server.tool()
    def research_security_list(research_run_id: str) -> str:
        """List names under study in a research run."""
        return _run(
            lambda: research_runs_service.list_securities(research_run_id)
        )

    @server.tool()
    def research_evidence_append(
        research_run_id: str,
        record_type: str,
        payload: dict[str, Any] | list[Any] | str | int | float | bool | None,
        record_id: str | None = None,
        as_of: int | None = None,
        security_id: str | None = None,
        symbol: str | None = None,
        id: str | None = None,
    ) -> str:
        """Append one immutable evidence record (jsonl-equivalent)."""
        return _run(
            lambda: research_runs_service.append_evidence(
                AppendResearchEvidenceInput(
                    id=id,
                    research_run_id=research_run_id,
                    record_type=record_type,
                    record_id=record_id,
                    payload=payload,
                    as_of=as_of,
                    security_id=security_id,
                    symbol=symbol,
                )
            )
        )

    @server.tool()
    def research_evidence_list(
        research_run_id: str,
        record_type: str | None = None,
        symbol: str | None = None,
        from_seq: int | None = None,
        limit: int = 1000,
    ) -> str:
        """List evidence for a research run (seq ascending)."""
        return _run(
            lambda: research_runs_service.list_evidence(
                research_run_id,
                record_type=record_type,
                symbol=symbol,
                from_seq=from_seq,
                limit=limit,
            )
        )

    @server.tool()
    def research_link_portfolio(
        research_run_id: str,
        portfolio_id: str,
        investment_case_id: str | None = None,
        link_role: Literal[
            "ADMISSION", "CONTEXT", "REBALANCE_INPUT", "THESIS_VALIDATION"
        ] = "ADMISSION",
        notes: str | None = None,
        id: str | None = None,
    ) -> str:
        """Bridge a finished research run into a portfolio workflow."""
        return _run(
            lambda: research_runs_service.link_to_portfolio(
                CreateResearchPortfolioLinkInput(
                    id=id,
                    research_run_id=research_run_id,
                    portfolio_id=portfolio_id,
                    investment_case_id=investment_case_id,
                    link_role=link_role,
                    notes=notes,
                )
            )
        )

    @server.tool()
    def research_links_by_portfolio(portfolio_id: str) -> str:
        """List research↔portfolio links for a portfolio."""
        return _run(
            lambda: research_runs_service.list_links_by_portfolio(portfolio_id)
        )

    @server.tool()
    def research_links_by_run(research_run_id: str) -> str:
        """List research↔portfolio links for a research run."""
        return _run(
            lambda: research_runs_service.list_portfolio_links(research_run_id)
        )

    @server.tool()
    def research_links_by_case(investment_case_id: str) -> str:
        """List research↔portfolio links for an investment case."""
        return _run(
            lambda: research_runs_service.list_links_by_investment_case(
                investment_case_id
            )
        )

    @server.tool()
    def research_unlink_portfolio(link_id: str) -> str:
        """Remove a research↔portfolio link."""
        return _run(
            lambda: (
                research_runs_service.unlink_from_portfolio(link_id),
                {"deleted": True, "id": link_id},
            )[1]
        )

    @server.tool()
    def research_security_remove(id: str) -> str:
        """Remove a security attachment from a research run."""
        return _run(
            lambda: (
                research_runs_service.remove_security(id),
                {"deleted": True, "id": id},
            )[1]
        )

    @server.tool()
    def research_run_delete(id: str) -> str:
        """Delete a research run and its evidence/links."""
        return _run(
            lambda: (
                research_runs_service.delete(id),
                {"deleted": True, "id": id},
            )[1]
        )

    @server.tool()
    def research_evidence_append_many(
        research_run_id: str,
        records: list[dict[str, Any]],
    ) -> str:
        """Append multiple evidence records to a research run in order."""
        return _run(
            lambda: research_runs_service.append_evidence_many(
                research_run_id,
                [
                    AppendResearchEvidenceInput(
                        research_run_id=research_run_id,
                        record_type=str(rec["record_type"]),
                        payload=rec.get("payload", {}),
                        id=rec.get("id"),
                        record_id=rec.get("record_id"),
                        as_of=rec.get("as_of"),
                        security_id=rec.get("security_id"),
                        symbol=rec.get("symbol"),
                    )
                    for rec in records
                ],
            )
        )

    # --- Trade proposals ---
    @server.tool()
    def trade_proposal_create(
        portfolio_id: str,
        trades: list[dict[str, Any]],
        price_as_of: int,
        rationale: str | None = None,
        warnings: list[str] | None = None,
        expires_at: int | None = None,
        id: str | None = None,
    ) -> str:
        """Persist a DRAFT paper-trade proposal. Does not change cash or holdings."""
        return _run(
            lambda: trade_proposals_service.create(
                CreateTradeProposalInput(
                    id=id,
                    portfolio_id=portfolio_id,
                    trades=[ProposedTrade.model_validate(t) for t in trades],
                    rationale=rationale,
                    warnings=warnings,
                    price_as_of=price_as_of,
                    expires_at=expires_at,
                )
            )
        )

    @server.tool()
    def trade_proposal_get(id: str) -> str:
        """Get a paper-trade proposal and its current persisted status."""
        return _run(lambda: trade_proposals_service.get_by_id(id))

    @server.tool()
    def trade_proposal_list(
        portfolio_id: str,
        status: Literal[
            "DRAFT", "APPROVED", "REJECTED", "SUPERSEDED", "EXECUTED"
        ]
        | None = None,
    ) -> str:
        """List proposals for a portfolio, optionally filtered by status."""
        return _run(
            lambda: trade_proposals_service.list_by_portfolio(
                portfolio_id, status
            )
        )

    @server.tool()
    def trade_proposal_approve(
        id: str, approved_at: int | None = None
    ) -> str:
        """Persist explicit user approval for a DRAFT proposal ID."""
        return _run(
            lambda: trade_proposals_service.approve(id, approved_at)
        )

    @server.tool()
    def trade_proposal_reject(
        id: str, rejected_at: int | None = None
    ) -> str:
        """Reject a DRAFT proposal."""
        return _run(lambda: trade_proposals_service.reject(id, rejected_at))

    @server.tool()
    def trade_proposal_supersede(
        id: str, superseded_at: int | None = None
    ) -> str:
        """Supersede a DRAFT proposal after creating a refreshed replacement."""
        return _run(
            lambda: trade_proposals_service.supersede(id, superseded_at)
        )

    @server.tool()
    def trade_proposal_execute(id: str, executed_at: int) -> str:
        """Atomically record every trade in one APPROVED proposal as EXECUTED."""
        return _run(
            lambda: trade_proposals_service.execute(id, executed_at)
        )

    @server.tool()
    def market_price_get(security_id: str, price_date: str) -> str:
        """Get a stored price for a security on YYYY-MM-DD."""
        return _run(lambda: market_prices_service.get(security_id, price_date))

    @server.tool()
    def market_price_upsert_many(prices: list[dict[str, Any]]) -> str:
        """Upsert many daily mark prices."""
        return _run(
            lambda: [
                market_prices_service.upsert(
                    UpsertMarketPriceInput(
                        security_id=str(p["security_id"]),
                        price_date=str(p["price_date"]),
                        price_paise=int(p["price_paise"]),
                        currency=str(p.get("currency") or "INR"),
                        source=p.get("source"),
                        captured_at=p.get("captured_at"),
                    )
                )
                for p in prices
            ]
        )

    @server.tool()
    def market_price_delete(security_id: str, price_date: str) -> str:
        """Delete a stored price row."""
        return _run(
            lambda: (
                market_prices_service.delete(security_id, price_date),
                {"deleted": True, "security_id": security_id, "price_date": price_date},
            )[1]
        )

    return server


mcp = create_db_mcp_server()


def main() -> None:
    """Load env, migrate schema, serve Midas DB tools over stdio MCP."""
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    configure()
    run_migrations()
    logging.info("midas-db MCP ready (db=%s)", get_db_path())
    # Hosts speak MCP over stdin/stdout — log only to stderr.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

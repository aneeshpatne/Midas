"""LangChain tools wrapping Midas DB services (same surface as midas-db-mcp).

DeepAgents call these in-process; external hosts use ``midas-db-mcp`` over stdio.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel

from midas.db.connection import configure, get_db_path
from midas.db.errors import MidasDbError
from midas.db.helpers import now_ms
from midas.db.migrate import run_migrations
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
    CreateTransactionInput,
    UpdateCompanyInput,
    UpdateInvestmentCaseInput,
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
    transactions_service,
)

_log = logging.getLogger(__name__)
_MIGRATIONS_DONE = False


def ensure_midas_db() -> str:
    """Apply migrations once per process; return the resolved DB path."""
    global _MIGRATIONS_DONE
    configure()
    if not _MIGRATIONS_DONE:
        run_migrations()
        _MIGRATIONS_DONE = True
        _log.info("Midas DB ready at %s", get_db_path())
    return str(get_db_path())


def _dump(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_dump(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _dump(v) for k, v in obj.items()}
    return obj


def _ok(data: Any) -> str:
    return json.dumps({"ok": True, "data": _dump(data)}, default=str)


def _fail(error: BaseException) -> str:
    return json.dumps(
        {
            "ok": False,
            "error": {"name": type(error).__name__, "message": str(error)},
        }
    )


def _run(fn: Any) -> str:
    try:
        ensure_midas_db()
        return _ok(fn())
    except MidasDbError as exc:
        return _fail(exc)
    except Exception as exc:  # noqa: BLE001 — surface to agent JSON
        _log.exception("midas db tool failed")
        return _fail(exc)


# ---------------------------------------------------------------------------
# Research runs (primary durable store for diligence)
# ---------------------------------------------------------------------------


@tool("research_run_create")
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
    """Create an isolated equity-research run in Midas DB.

    Returns run id — use it for all later writes.
    """
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


@tool("research_run_get")
def research_run_get(id: str) -> str:
    """Get research run metadata by id."""
    return _run(lambda: research_runs_service.get_by_id(id))


@tool("research_run_get_bundle")
def research_run_get_bundle(id: str) -> str:
    """Get research run with securities, full evidence ledger, and portfolio links."""
    return _run(lambda: research_runs_service.get_bundle(id))


@tool("research_run_list")
def research_run_list(
    slug: str | None = None,
    status: Literal[
        "DRAFT", "IN_PROGRESS", "COMPLETED", "BLOCKED", "ABANDONED"
    ]
    | None = None,
    workflow: Literal["single_stock", "named_comparison", "broad_universe"]
    | None = None,
    limit: int = 50,
) -> str:
    """List research runs (newest first). Prefer the active run id from this session."""
    return _run(
        lambda: research_runs_service.list(
            slug=slug, status=status, workflow=workflow, limit=limit
        )
    )


@tool("research_run_set_mandate")
def research_run_set_mandate(id: str, mandate_md: str) -> str:
    """Write/replace the frozen mandate text on a research run."""
    return _run(lambda: research_runs_service.set_mandate(id, mandate_md))


@tool("research_run_set_report")
def research_run_set_report(id: str, report_md: str) -> str:
    """Write/replace the IC decision report text on a research run (DB-only deliverable)."""
    return _run(lambda: research_runs_service.set_report(id, report_md))


@tool("research_run_complete")
def research_run_complete(id: str, report_md: str | None = None) -> str:
    """Mark research run COMPLETED. Requires mandate; report_md required unless already set."""
    return _run(lambda: research_runs_service.complete(id, report_md))


@tool("research_run_set_status")
def research_run_set_status(
    id: str,
    status: Literal[
        "DRAFT", "IN_PROGRESS", "COMPLETED", "BLOCKED", "ABANDONED"
    ],
) -> str:
    """Set research run status without completing."""
    return _run(lambda: research_runs_service.set_status(id, status))


@tool("research_run_update")
def research_run_update(
    id: str,
    title: str | None = None,
    universe_or_company: str | None = None,
    horizon_text: str | None = None,
    horizon_months: int | None = None,
    mandate_md: str | None = None,
    report_md: str | None = None,
    primary_runtime: str | None = None,
    execution_mode: str | None = None,
    status: Literal[
        "DRAFT", "IN_PROGRESS", "COMPLETED", "BLOCKED", "ABANDONED"
    ]
    | None = None,
) -> str:
    """Patch research run fields. Omitted fields are left unchanged."""
    patch: dict[str, Any] = {}
    for key, val in {
        "title": title,
        "universe_or_company": universe_or_company,
        "horizon_text": horizon_text,
        "horizon_months": horizon_months,
        "mandate_md": mandate_md,
        "report_md": report_md,
        "primary_runtime": primary_runtime,
        "execution_mode": execution_mode,
        "status": status,
    }.items():
        if val is not None:
            patch[key] = val
    return _run(
        lambda: research_runs_service.update(id, UpdateResearchRunInput(**patch))
    )


@tool("research_security_add")
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
) -> str:
    """Attach a symbol under study to a research run."""
    return _run(
        lambda: research_runs_service.add_security(
            AddResearchRunSecurityInput(
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


@tool("research_security_list")
def research_security_list(research_run_id: str) -> str:
    """List names under study on a research run."""
    return _run(lambda: research_runs_service.list_securities(research_run_id))


@tool("research_evidence_append")
def research_evidence_append(
    research_run_id: str,
    record_type: str,
    payload: dict[str, Any] | list[Any] | str | int | float | bool | None,
    record_id: str | None = None,
    as_of: int | None = None,
    security_id: str | None = None,
    symbol: str | None = None,
) -> str:
    """Append one immutable evidence/stage record (sources, calcs, screen results, decisions)."""
    return _run(
        lambda: research_runs_service.append_evidence(
            AppendResearchEvidenceInput(
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


@tool("research_evidence_list")
def research_evidence_list(
    research_run_id: str,
    record_type: str | None = None,
    symbol: str | None = None,
    from_seq: int | None = None,
    limit: int = 1000,
) -> str:
    """List evidence rows for a research run (seq ascending)."""
    return _run(
        lambda: research_runs_service.list_evidence(
            research_run_id,
            record_type=record_type,
            symbol=symbol,
            from_seq=from_seq,
            limit=limit,
        )
    )


@tool("research_link_portfolio")
def research_link_portfolio(
    research_run_id: str,
    portfolio_id: str,
    investment_case_id: str | None = None,
    link_role: Literal[
        "ADMISSION", "CONTEXT", "REBALANCE_INPUT", "THESIS_VALIDATION"
    ] = "ADMISSION",
    notes: str | None = None,
) -> str:
    """Bridge a finished research run into a paper portfolio workflow."""
    return _run(
        lambda: research_runs_service.link_to_portfolio(
            CreateResearchPortfolioLinkInput(
                research_run_id=research_run_id,
                portfolio_id=portfolio_id,
                investment_case_id=investment_case_id,
                link_role=link_role,
                notes=notes,
            )
        )
    )


# ---------------------------------------------------------------------------
# Master data + paper portfolio (for resolution and post-research admission)
# ---------------------------------------------------------------------------


@tool("company_create")
def company_create(
    name: str,
    legal_name: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
    market_cap_bucket: Literal["LARGE", "MID", "SMALL", "MICRO", "OTHER"]
    | None = None,
    country_code: str = "IN",
    website: str | None = None,
    notes: str | None = None,
    id: str | None = None,
) -> str:
    """Create issuer metadata in Midas DB."""
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
                notes=notes,
            )
        )
    )


@tool("company_get")
def company_get(id: str) -> str:
    """Get a company by id."""
    return _run(lambda: companies_service.get_by_id(id))


@tool("company_list")
def company_list(
    sector: str | None = None,
    industry: str | None = None,
    market_cap_bucket: Literal["LARGE", "MID", "SMALL", "MICRO", "OTHER"]
    | None = None,
    limit: int = 200,
) -> str:
    """List companies with optional filters."""
    return _run(
        lambda: companies_service.list(
            sector=sector,
            industry=industry,
            market_cap_bucket=market_cap_bucket,
            limit=limit,
        )
    )


@tool("company_update")
def company_update(
    id: str,
    name: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
    market_cap_bucket: Literal["LARGE", "MID", "SMALL", "MICRO", "OTHER"]
    | None = None,
    notes: str | None = None,
) -> str:
    """Update company fields."""
    patch: dict[str, Any] = {}
    for key, val in {
        "name": name,
        "sector": sector,
        "industry": industry,
        "market_cap_bucket": market_cap_bucket,
        "notes": notes,
    }.items():
        if val is not None:
            patch[key] = val
    return _run(lambda: companies_service.update(id, UpdateCompanyInput(**patch)))


@tool("security_create")
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
            )
        )
    )


@tool("security_get")
def security_get(id: str, with_company: bool = True) -> str:
    """Get a security by id."""
    if with_company:
        return _run(lambda: securities_service.get_by_id_with_company(id))
    return _run(lambda: securities_service.get_by_id(id))


@tool("security_get_by_ticker")
def security_get_by_ticker(exchange: str, ticker: str) -> str:
    """Lookup security by exchange + ticker."""
    return _run(
        lambda: securities_service.get_by_exchange_ticker(exchange, ticker)
    )


@tool("security_list")
def security_list(
    active_only: bool = False, company_id: str | None = None
) -> str:
    """List securities."""
    return _run(
        lambda: securities_service.list(
            active_only=active_only, company_id=company_id
        )
    )


@tool("security_link_company")
def security_link_company(
    security_id: str, company_id: str | None = None
) -> str:
    """Link or unlink security to company (null company_id unlinks)."""
    return _run(lambda: securities_service.link_company(security_id, company_id))


@tool("security_update")
def security_update(
    id: str,
    name: str | None = None,
    is_active: bool | None = None,
    company_id: str | None = None,
    clear_company: bool = False,
) -> str:
    """Update security metadata."""
    patch: dict[str, Any] = {}
    if clear_company:
        patch["company_id"] = None
    elif company_id is not None:
        patch["company_id"] = company_id
    if name is not None:
        patch["name"] = name
    if is_active is not None:
        patch["is_active"] = is_active
    return _run(lambda: securities_service.update(id, UpdateSecurityInput(**patch)))


@tool("portfolio_create")
def portfolio_create(
    name: str,
    description: str | None = None,
    strategy: str | None = None,
    base_currency: str = "INR",
    target_capital_paise: int | None = None,
    id: str | None = None,
) -> str:
    """Create a paper portfolio."""
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


@tool("portfolio_get")
def portfolio_get(id: str) -> str:
    """Get a portfolio by id."""
    return _run(lambda: portfolios_service.get_by_id(id))


@tool("portfolio_list")
def portfolio_list(include_archived: bool = False) -> str:
    """List paper portfolios."""
    return _run(
        lambda: portfolios_service.list(include_archived=include_archived)
    )


@tool("portfolio_update")
def portfolio_update(
    id: str,
    name: str | None = None,
    description: str | None = None,
    strategy: str | None = None,
    target_capital_paise: int | None = None,
) -> str:
    """Update portfolio metadata."""
    patch: dict[str, Any] = {}
    for key, val in {
        "name": name,
        "description": description,
        "strategy": strategy,
        "target_capital_paise": target_capital_paise,
    }.items():
        if val is not None:
            patch[key] = val
    return _run(
        lambda: portfolios_service.update(id, UpdatePortfolioInput(**patch))
    )


@tool("portfolio_cash_summary")
def portfolio_cash_summary(portfolio_id: str) -> str:
    """Cash and funding snapshot from the transaction ledger."""
    return _run(lambda: portfolios_service.get_cash_summary(portfolio_id))


@tool("account_create")
def account_create(
    portfolio_id: str,
    name: str,
    institution: str | None = None,
    account_reference: str | None = None,
    currency: str = "INR",
    id: str | None = None,
) -> str:
    """Create a custody sleeve inside a portfolio."""
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


@tool("account_list")
def account_list(portfolio_id: str) -> str:
    """List accounts for a portfolio."""
    return _run(
        lambda: portfolio_accounts_service.list_by_portfolio(portfolio_id)
    )


@tool("investment_case_create")
def investment_case_create(
    portfolio_id: str,
    security_id: str,
    name: str,
    status: Literal[
        "WATCHLIST", "ACTIVE", "REDUCING", "EXITED", "INVALIDATED", "ARCHIVED"
    ] = "WATCHLIST",
    conviction: int | None = None,
    time_horizon_months: int | None = None,
    id: str | None = None,
) -> str:
    """Create a thesis-backed position intent in a paper portfolio."""
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
            )
        )
    )


@tool("investment_case_list")
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


@tool("investment_case_update")
def investment_case_update(
    id: str,
    name: str | None = None,
    status: Literal[
        "WATCHLIST", "ACTIVE", "REDUCING", "EXITED", "INVALIDATED", "ARCHIVED"
    ]
    | None = None,
    conviction: int | None = None,
) -> str:
    """Update investment case fields."""
    patch: dict[str, Any] = {}
    for key, val in {
        "name": name,
        "status": status,
        "conviction": conviction,
    }.items():
        if val is not None:
            patch[key] = val
    return _run(
        lambda: investment_cases_service.update(
            id, UpdateInvestmentCaseInput(**patch)
        )
    )


@tool("thesis_revision_create")
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
) -> str:
    """Append a thesis revision to an investment case."""
    return _run(
        lambda: thesis_revisions_service.create(
            CreateThesisRevisionInput(
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
            )
        )
    )


@tool("thesis_revision_list")
def thesis_revision_list(investment_case_id: str) -> str:
    """List thesis revisions for a case."""
    return _run(lambda: thesis_revisions_service.list_by_case(investment_case_id))


@tool("transaction_create")
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
    notes: str | None = None,
) -> str:
    """Record a paper cash or position ledger event (not a broker order)."""
    return _run(
        lambda: transactions_service.create(
            CreateTransactionInput(
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
                executed_at=executed_at if executed_at is not None else now_ms(),
                notes=notes,
            )
        )
    )


@tool("transaction_list")
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
) -> str:
    """List portfolio transactions."""
    return _run(
        lambda: transactions_service.list_by_portfolio(
            portfolio_id, type_=type, security_id=security_id
        )
    )


@tool("market_price_upsert")
def market_price_upsert(
    security_id: str,
    price_date: str,
    price_paise: int,
    currency: str = "INR",
    source: str | None = None,
) -> str:
    """Upsert a daily mark-to-market price (YYYY-MM-DD, integer paise)."""
    return _run(
        lambda: market_prices_service.upsert(
            UpsertMarketPriceInput(
                security_id=security_id,
                price_date=price_date,
                price_paise=price_paise,
                currency=currency,
                source=source,
            )
        )
    )


@tool("market_price_latest")
def market_price_latest(security_id: str) -> str:
    """Latest stored mark price for a security."""
    return _run(lambda: market_prices_service.latest(security_id))


MIDAS_DB_TOOLS: tuple[BaseTool, ...] = (
    research_run_create,
    research_run_get,
    research_run_get_bundle,
    research_run_list,
    research_run_set_mandate,
    research_run_set_report,
    research_run_complete,
    research_run_set_status,
    research_run_update,
    research_security_add,
    research_security_list,
    research_evidence_append,
    research_evidence_list,
    research_link_portfolio,
    company_create,
    company_get,
    company_list,
    company_update,
    security_create,
    security_get,
    security_get_by_ticker,
    security_list,
    security_link_company,
    security_update,
    portfolio_create,
    portfolio_get,
    portfolio_list,
    portfolio_update,
    portfolio_cash_summary,
    account_create,
    account_list,
    investment_case_create,
    investment_case_list,
    investment_case_update,
    thesis_revision_create,
    thesis_revision_list,
    transaction_create,
    transaction_list,
    market_price_upsert,
    market_price_latest,
)

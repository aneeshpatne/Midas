"""Tests for Midas DB schema, services, and MCP registration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from midas.db.connection import close, configure, get_connection
from midas.db.errors import NotFoundError, ValidationError
from midas.db.helpers import now_ms
from midas.db.migrate import run_migrations
from midas.db.models import (
    AddResearchRunSecurityInput,
    AppendResearchEvidenceInput,
    CreateCompanyInput,
    CreateInvestmentCaseInput,
    CreatePortfolioInput,
    CreateResearchPortfolioLinkInput,
    CreateResearchRunInput,
    CreateSecurityInput,
    CreateThesisRevisionInput,
    CreateTransactionInput,
    UpsertMarketPriceInput,
)
from midas.db.services import (
    companies_service,
    investment_cases_service,
    market_prices_service,
    portfolios_service,
    research_runs_service,
    securities_service,
    thesis_revisions_service,
    transactions_service,
)
from midas.db_mcp_server import create_db_mcp_server


@pytest.fixture()
def midas_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test-midas.db"
    monkeypatch.setenv("MIDAS_DB_PATH", str(db_path))
    close()
    configure(db_path)
    run_migrations()
    yield db_path
    close()


def test_migrations_create_core_tables(midas_db: Path) -> None:
    conn = get_connection()
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {
        "schema_migrations",
        "companies",
        "securities",
        "portfolios",
        "portfolio_accounts",
        "investment_cases",
        "thesis_revisions",
        "transactions",
        "market_prices",
        "research_runs",
        "research_evidence",
        "research_run_securities",
        "research_portfolio_links",
    } <= tables
    versions = {
        row[0]
        for row in conn.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall()
    }
    assert versions == {1, 2, 3}


def test_portfolio_deposit_buy_cash_summary(midas_db: Path) -> None:
    company = companies_service.create(
        CreateCompanyInput(name="Reliance Industries", sector="Energy")
    )
    security = securities_service.create(
        CreateSecurityInput(
            ticker="RELIANCE",
            exchange="NSE",
            name="Reliance Industries Ltd",
            currency="INR",
            company_id=company.id,
        )
    )
    portfolio = portfolios_service.create(
        CreatePortfolioInput(
            name="Demo book",
            target_capital_paise=10_000_00,  # ₹10,000
        )
    )
    deposit = transactions_service.create(
        CreateTransactionInput(
            portfolio_id=portfolio.id,
            type="DEPOSIT",
            gross_amount_paise=10_000_00,
            executed_at=now_ms(),
        )
    )
    assert deposit.cash_effect_paise == 10_000_00

    buy = transactions_service.create(
        CreateTransactionInput(
            portfolio_id=portfolio.id,
            security_id=security.id,
            type="BUY",
            quantity_micros=1_000_000,  # 1 share
            price_paise=2_500_00,  # ₹2,500
            executed_at=now_ms(),
        )
    )
    assert buy.cash_effect_paise == -2_500_00
    assert buy.gross_amount_paise == 2_500_00

    summary = portfolios_service.get_cash_summary(portfolio.id)
    assert summary.cash_balance_paise == 7_500_00
    assert summary.total_deposits_paise == 10_000_00
    assert summary.net_contributed_capital_paise == 10_000_00
    assert summary.remaining_to_contribute_paise == 0


def test_investment_case_and_thesis(midas_db: Path) -> None:
    sec = securities_service.create(
        CreateSecurityInput(
            ticker="TCS",
            exchange="NSE",
            name="TCS",
            currency="INR",
        )
    )
    pf = portfolios_service.create(CreatePortfolioInput(name="Core"))
    case = investment_cases_service.create(
        CreateInvestmentCaseInput(
            portfolio_id=pf.id,
            security_id=sec.id,
            name="TCS core holding",
            conviction=4,
        )
    )
    rev = thesis_revisions_service.create(
        CreateThesisRevisionInput(
            investment_case_id=case.id,
            thesis="Durable franchise with cash generation.",
            conviction=4,
        )
    )
    assert rev.revision_number == 1
    assert rev.revision_type == "INITIAL"
    rev2 = thesis_revisions_service.create(
        CreateThesisRevisionInput(
            investment_case_id=case.id,
            thesis="Updated after results.",
            revision_type="EARNINGS_UPDATE",
        )
    )
    assert rev2.revision_number == 2
    assert len(thesis_revisions_service.list_by_case(case.id)) == 2


def test_research_run_evidence_and_link(midas_db: Path) -> None:
    run = research_runs_service.create(
        CreateResearchRunInput(
            slug="reliance-7y",
            workflow="single_stock",
            universe_or_company="Reliance Industries",
            horizon_text="7 years",
            horizon_months=84,
        )
    )
    research_runs_service.set_mandate(run.id, "# Mandate\n\nScope frozen.")
    research_runs_service.add_security(
        AddResearchRunSecurityInput(
            research_run_id=run.id,
            symbol="RELIANCE",
            exchange="NSE",
        )
    )
    evidence = research_runs_service.append_evidence(
        AppendResearchEvidenceInput(
            research_run_id=run.id,
            record_type="source",
            payload={"url": "https://example.com", "note": "AR"},
            symbol="RELIANCE",
        )
    )
    assert evidence.seq == 1
    research_runs_service.complete(run.id, report_md="# Report\n\nDone.")
    completed = research_runs_service.get_by_id(run.id)
    assert completed.status == "COMPLETED"
    assert completed.completed_at is not None

    pf = portfolios_service.create(CreatePortfolioInput(name="Link target"))
    link = research_runs_service.link_to_portfolio(
        CreateResearchPortfolioLinkInput(
            research_run_id=run.id,
            portfolio_id=pf.id,
            link_role="ADMISSION",
        )
    )
    assert link.portfolio_id == pf.id
    bundle = research_runs_service.get_bundle(run.id)
    assert len(bundle.securities) == 1
    assert len(bundle.evidence) == 1
    assert len(bundle.portfolio_links) == 1


def test_market_price_upsert(midas_db: Path) -> None:
    sec = securities_service.create(
        CreateSecurityInput(
            ticker="INFY", exchange="NSE", name="Infosys", currency="INR"
        )
    )
    p1 = market_prices_service.upsert(
        UpsertMarketPriceInput(
            security_id=sec.id,
            price_date="2026-08-01",
            price_paise=1500_00,
        )
    )
    p2 = market_prices_service.upsert(
        UpsertMarketPriceInput(
            security_id=sec.id,
            price_date="2026-08-01",
            price_paise=1510_00,
        )
    )
    assert p1.price_paise == 1500_00
    assert p2.price_paise == 1510_00
    assert market_prices_service.latest(sec.id).price_paise == 1510_00


def test_not_found_and_validation(midas_db: Path) -> None:
    with pytest.raises(NotFoundError):
        portfolios_service.get_by_id("missing")
    with pytest.raises(ValidationError):
        portfolios_service.create(CreatePortfolioInput(name="   "))
    with pytest.raises(ValidationError):
        research_runs_service.create(
            CreateResearchRunInput(
                slug="Bad Slug",
                workflow="single_stock",
                universe_or_company="X",
                horizon_text="1y",
            )
        )


def test_db_mcp_registers_tools(midas_db: Path) -> None:
    server = create_db_mcp_server()
    names = set(server._tool_manager._tools)  # noqa: SLF001
    assert "portfolio_create" in names
    assert "transaction_create" in names
    assert "research_run_create" in names
    assert "company_create" in names
    assert "security_create" in names


@pytest.mark.asyncio
async def test_db_mcp_portfolio_tool_roundtrip(midas_db: Path) -> None:
    server = create_db_mcp_server()
    result = await server.call_tool(
        "portfolio_create",
        {"name": "MCP book", "target_capital_paise": 1_000_00},
    )
    # FastMCP may return CallToolResult or tuple
    if hasattr(result, "content"):
        text = result.content[0].text
    elif isinstance(result, tuple):
        text = result[0][0].text
    else:
        text = str(result)
    payload = json.loads(text)
    assert payload["ok"] is True
    assert payload["data"]["name"] == "MCP book"

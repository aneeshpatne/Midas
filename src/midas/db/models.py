"""Pydantic models for Midas DB entities and inputs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SecurityType = Literal[
    "EQUITY", "ETF", "MUTUAL_FUND", "BOND", "REIT", "CRYPTO", "OTHER"
]
InvestmentCaseStatus = Literal[
    "WATCHLIST", "ACTIVE", "REDUCING", "EXITED", "INVALIDATED", "ARCHIVED"
]
ThesisRevisionType = Literal[
    "INITIAL",
    "UPDATE",
    "EARNINGS_UPDATE",
    "RISK_UPDATE",
    "INVALIDATION",
    "EXIT_NOTE",
]
TransactionType = Literal[
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
MarketCapBucket = Literal["LARGE", "MID", "SMALL", "MICRO", "OTHER"]
ResearchWorkflow = Literal["single_stock", "named_comparison", "broad_universe"]
ResearchRunStatus = Literal[
    "DRAFT", "IN_PROGRESS", "COMPLETED", "BLOCKED", "ABANDONED"
]
ResearchSecurityRole = Literal[
    "SUBJECT", "PEER", "BENCHMARK", "NEAR_MISS", "EXCLUDED"
]
ResearchPortfolioLinkRole = Literal[
    "ADMISSION", "CONTEXT", "REBALANCE_INPUT", "THESIS_VALIDATION"
]
Conviction = Literal[1, 2, 3, 4, 5]
TradeProposalStatus = Literal[
    "DRAFT", "APPROVED", "REJECTED", "SUPERSEDED", "EXECUTED"
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)


class Company(_Model):
    id: str
    name: str
    legal_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_bucket: MarketCapBucket | None = None
    country_code: str = "IN"
    website: str | None = None
    classification_source: str | None = None
    classification_as_of: str | None = None
    notes: str | None = None
    created_at: int
    updated_at: int


class Security(_Model):
    id: str
    company_id: str | None = None
    ticker: str
    exchange: str
    name: str
    security_type: SecurityType = "EQUITY"
    currency: str
    isin: str | None = None
    is_active: bool = True
    created_at: int
    updated_at: int


class SecurityWithCompany(Security):
    company: Company | None = None


class Portfolio(_Model):
    id: str
    name: str
    description: str | None = None
    strategy: str | None = None
    base_currency: str = "INR"
    target_capital_paise: int | None = None
    created_at: int
    updated_at: int
    archived_at: int | None = None


class PortfolioAccount(_Model):
    id: str
    portfolio_id: str
    name: str
    institution: str | None = None
    account_reference: str | None = None
    currency: str = "INR"
    created_at: int
    updated_at: int


class InvestmentCase(_Model):
    id: str
    portfolio_id: str
    security_id: str
    name: str
    status: InvestmentCaseStatus = "WATCHLIST"
    conviction: Conviction | None = None
    time_horizon_months: int | None = None
    opened_at: int | None = None
    closed_at: int | None = None
    created_at: int
    updated_at: int


class ThesisRevision(_Model):
    id: str
    investment_case_id: str
    revision_number: int
    revision_type: ThesisRevisionType = "UPDATE"
    thesis: str
    bull_case: str | None = None
    base_case: str | None = None
    bear_case: str | None = None
    catalysts: str | None = None
    risks: str | None = None
    invalidation_conditions: str | None = None
    target_price_paise: int | None = None
    conviction: Conviction | None = None
    effective_at: int
    created_at: int


class ProposedTrade(_Model):
    type: Literal["BUY", "SELL"]
    security_id: str
    account_id: str | None = None
    investment_case_id: str | None = None
    quantity_micros: int
    price_paise: int
    fees_paise: int = 0
    taxes_paise: int = 0
    currency: str | None = None
    settlement_date: str | None = None
    notes: str | None = None


class TradeProposal(_Model):
    id: str
    portfolio_id: str
    status: TradeProposalStatus = "DRAFT"
    trades_json: str
    rationale: str | None = None
    warnings_json: str = "[]"
    price_as_of: int
    expires_at: int | None = None
    approved_at: int | None = None
    rejected_at: int | None = None
    superseded_at: int | None = None
    executed_at: int | None = None
    created_at: int
    updated_at: int


class TradeProposalView(_Model):
    id: str
    portfolio_id: str
    status: TradeProposalStatus
    trades: list[ProposedTrade]
    warnings: list[str] = Field(default_factory=list)
    rationale: str | None = None
    price_as_of: int
    expires_at: int | None = None
    approved_at: int | None = None
    rejected_at: int | None = None
    superseded_at: int | None = None
    executed_at: int | None = None
    created_at: int
    updated_at: int


class Transaction(_Model):
    id: str
    portfolio_id: str
    account_id: str | None = None
    security_id: str | None = None
    investment_case_id: str | None = None
    proposal_id: str | None = None
    type: TransactionType
    quantity_micros: int | None = None
    price_paise: int | None = None
    gross_amount_paise: int | None = None
    fees_paise: int = 0
    taxes_paise: int = 0
    net_amount_paise: int | None = None
    cash_effect_paise: int
    currency: str = "INR"
    exchange_rate_micros: int = 1_000_000
    executed_at: int
    settlement_date: str | None = None
    external_reference: str | None = None
    notes: str | None = None
    created_at: int


class PortfolioCashSummary(_Model):
    portfolio_id: str
    cash_balance_paise: int
    total_deposits_paise: int
    total_withdrawals_paise: int
    net_contributed_capital_paise: int
    target_capital_paise: int | None = None
    remaining_to_contribute_paise: int | None = None


class MarketPrice(_Model):
    security_id: str
    price_date: str
    price_paise: int
    currency: str = "INR"
    source: str | None = None
    captured_at: int


class CompanyStatsBucket(_Model):
    key: str
    company_count: int


class ResearchRun(_Model):
    id: str
    slug: str
    run_key: str
    workflow: ResearchWorkflow
    status: ResearchRunStatus = "IN_PROGRESS"
    title: str | None = None
    universe_or_company: str
    horizon_text: str
    horizon_months: int | None = None
    cutoff_at: int
    mandate_md: str | None = None
    report_md: str | None = None
    primary_runtime: str | None = None
    execution_mode: str | None = None
    created_at: int
    updated_at: int
    completed_at: int | None = None


class ResearchRunSecurity(_Model):
    id: str
    research_run_id: str
    security_id: str | None = None
    symbol: str
    exchange: str | None = None
    role: ResearchSecurityRole = "SUBJECT"
    sort_order: int = 0
    notes: str | None = None
    created_at: int


class ResearchEvidence(_Model):
    id: str
    research_run_id: str
    record_type: str
    record_id: str | None = None
    seq: int
    payload_json: str
    as_of: int | None = None
    security_id: str | None = None
    symbol: str | None = None
    created_at: int


class ResearchPortfolioLink(_Model):
    id: str
    research_run_id: str
    portfolio_id: str
    investment_case_id: str | None = None
    link_role: ResearchPortfolioLinkRole = "ADMISSION"
    notes: str | None = None
    created_at: int


class ResearchRunBundle(_Model):
    run: ResearchRun
    securities: list[ResearchRunSecurity]
    evidence: list[ResearchEvidence]
    portfolio_links: list[ResearchPortfolioLink]


# --- Create / update inputs ---


class CreateCompanyInput(_Model):
    id: str | None = None
    name: str
    legal_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_bucket: MarketCapBucket | None = None
    country_code: str = "IN"
    website: str | None = None
    classification_source: str | None = None
    classification_as_of: str | None = None
    notes: str | None = None


class UpdateCompanyInput(_Model):
    name: str | None = None
    legal_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_bucket: MarketCapBucket | None = None
    country_code: str | None = None
    website: str | None = None
    classification_source: str | None = None
    classification_as_of: str | None = None
    notes: str | None = None


class CreateSecurityInput(_Model):
    id: str | None = None
    company_id: str | None = None
    ticker: str
    exchange: str
    name: str
    security_type: SecurityType = "EQUITY"
    currency: str
    isin: str | None = None
    is_active: bool = True


class UpdateSecurityInput(_Model):
    company_id: str | None = None
    ticker: str | None = None
    exchange: str | None = None
    name: str | None = None
    security_type: SecurityType | None = None
    currency: str | None = None
    isin: str | None = None
    is_active: bool | None = None


class CreatePortfolioInput(_Model):
    id: str | None = None
    name: str
    description: str | None = None
    strategy: str | None = None
    base_currency: str = "INR"
    target_capital_paise: int | None = None


class UpdatePortfolioInput(_Model):
    name: str | None = None
    description: str | None = None
    strategy: str | None = None
    base_currency: str | None = None
    target_capital_paise: int | None = None


class CreatePortfolioAccountInput(_Model):
    id: str | None = None
    portfolio_id: str
    name: str
    institution: str | None = None
    account_reference: str | None = None
    currency: str = "INR"


class UpdatePortfolioAccountInput(_Model):
    name: str | None = None
    institution: str | None = None
    account_reference: str | None = None
    currency: str | None = None


class CreateInvestmentCaseInput(_Model):
    id: str | None = None
    portfolio_id: str
    security_id: str
    name: str
    status: InvestmentCaseStatus = "WATCHLIST"
    conviction: Conviction | None = None
    time_horizon_months: int | None = None
    opened_at: int | None = None
    closed_at: int | None = None


class UpdateInvestmentCaseInput(_Model):
    name: str | None = None
    status: InvestmentCaseStatus | None = None
    conviction: Conviction | None = None
    time_horizon_months: int | None = None
    opened_at: int | None = None
    closed_at: int | None = None


class CreateThesisRevisionInput(_Model):
    id: str | None = None
    investment_case_id: str
    revision_type: ThesisRevisionType = "UPDATE"
    thesis: str
    bull_case: str | None = None
    base_case: str | None = None
    bear_case: str | None = None
    catalysts: str | None = None
    risks: str | None = None
    invalidation_conditions: str | None = None
    target_price_paise: int | None = None
    conviction: Conviction | None = None
    effective_at: int | None = None


class CreateTransactionInput(_Model):
    id: str | None = None
    portfolio_id: str
    account_id: str | None = None
    security_id: str | None = None
    investment_case_id: str | None = None
    proposal_id: str | None = None
    type: TransactionType
    quantity_micros: int | None = None
    price_paise: int | None = None
    gross_amount_paise: int | None = None
    fees_paise: int = 0
    taxes_paise: int = 0
    net_amount_paise: int | None = None
    cash_effect_paise: int | None = None
    currency: str = "INR"
    exchange_rate_micros: int = 1_000_000
    executed_at: int
    settlement_date: str | None = None
    external_reference: str | None = None
    notes: str | None = None


class CreateTradeProposalInput(_Model):
    id: str | None = None
    portfolio_id: str
    trades: list[ProposedTrade]
    rationale: str | None = None
    warnings: list[str] | None = None
    price_as_of: int
    expires_at: int | None = None


class UpsertMarketPriceInput(_Model):
    security_id: str
    price_date: str
    price_paise: int
    currency: str = "INR"
    source: str | None = None
    captured_at: int | None = None


class CreateResearchRunInput(_Model):
    id: str | None = None
    slug: str
    run_key: str | None = None
    workflow: ResearchWorkflow
    status: ResearchRunStatus = "IN_PROGRESS"
    title: str | None = None
    universe_or_company: str
    horizon_text: str
    horizon_months: int | None = None
    cutoff_at: int | None = None
    mandate_md: str | None = None
    report_md: str | None = None
    primary_runtime: str | None = None
    execution_mode: str | None = None


class UpdateResearchRunInput(_Model):
    title: str | None = None
    universe_or_company: str | None = None
    horizon_text: str | None = None
    horizon_months: int | None = None
    cutoff_at: int | None = None
    mandate_md: str | None = None
    report_md: str | None = None
    primary_runtime: str | None = None
    execution_mode: str | None = None
    status: ResearchRunStatus | None = None


class AddResearchRunSecurityInput(_Model):
    id: str | None = None
    research_run_id: str
    security_id: str | None = None
    symbol: str
    exchange: str | None = None
    role: ResearchSecurityRole = "SUBJECT"
    sort_order: int = 0
    notes: str | None = None


class AppendResearchEvidenceInput(_Model):
    id: str | None = None
    research_run_id: str
    record_type: str
    record_id: str | None = None
    payload: Any = Field(description="JSON-serializable evidence payload")
    as_of: int | None = None
    security_id: str | None = None
    symbol: str | None = None


class CreateResearchPortfolioLinkInput(_Model):
    id: str | None = None
    research_run_id: str
    portfolio_id: str
    investment_case_id: str | None = None
    link_role: ResearchPortfolioLinkRole = "ADMISSION"
    notes: str | None = None

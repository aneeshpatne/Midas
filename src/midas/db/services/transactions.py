"""Transactions and market prices services."""

from __future__ import annotations

import re

from midas.db.errors import NotFoundError, ValidationError
from midas.db.models import (
    CreateTransactionInput,
    MarketPrice,
    Transaction,
    TransactionType,
    UpsertMarketPriceInput,
)
from midas.db.repositories.investment_cases import investment_cases_repository
from midas.db.repositories.portfolios import (
    portfolio_accounts_repository,
    portfolios_repository,
)
from midas.db.repositories.securities import securities_repository
from midas.db.repositories.transactions import (
    market_prices_repository,
    transactions_repository,
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SECURITY_REQUIRED: set[TransactionType] = {
    "BUY",
    "SELL",
    "BONUS",
    "TRANSFER_IN",
    "TRANSFER_OUT",
}
PRICE_REQUIRED: set[TransactionType] = {"BUY", "SELL"}
CASH_AMOUNT_REQUIRED: set[TransactionType] = {
    "DEPOSIT",
    "WITHDRAWAL",
    "DIVIDEND",
    "INTEREST",
    "FEE",
    "TAX",
}


def compute_gross_amount_paise(
    quantity_micros: int | None, price_paise: int | None
) -> int | None:
    if quantity_micros is None or price_paise is None:
        return None
    return round((quantity_micros * price_paise) / 1_000_000)


def compute_net_cash_magnitude(
    *,
    type_: TransactionType,
    gross_amount_paise: int,
    fees_paise: int,
    taxes_paise: int,
) -> int:
    if type_ in {"BUY", "WITHDRAWAL", "FEE", "TAX"}:
        return gross_amount_paise + fees_paise + taxes_paise
    if type_ in {"SELL", "DEPOSIT", "DIVIDEND", "INTEREST"}:
        return gross_amount_paise - fees_paise - taxes_paise
    return gross_amount_paise


def compute_cash_effect_paise(
    *,
    type_: TransactionType,
    gross_amount_paise: int | None,
    fees_paise: int,
    taxes_paise: int,
) -> int:
    if type_ in {"SPLIT", "BONUS", "TRANSFER_IN", "TRANSFER_OUT"}:
        return 0
    if gross_amount_paise is None:
        raise ValidationError(
            f"gross_amount_paise is required to compute cash_effect for {type_}"
        )
    magnitude = compute_net_cash_magnitude(
        type_=type_,
        gross_amount_paise=gross_amount_paise,
        fees_paise=fees_paise,
        taxes_paise=taxes_paise,
    )
    if type_ in {"DEPOSIT", "SELL", "DIVIDEND", "INTEREST"}:
        return magnitude
    if type_ in {"BUY", "WITHDRAWAL", "FEE", "TAX"}:
        return -magnitude
    return 0


class TransactionsService:
    def get_by_id(self, id_: str) -> Transaction:
        tx = transactions_repository.find_by_id(id_)
        if not tx:
            raise NotFoundError("Transaction", id_)
        return tx

    def list_by_portfolio(
        self,
        portfolio_id: str,
        *,
        type_: TransactionType | None = None,
        security_id: str | None = None,
        investment_case_id: str | None = None,
        account_id: str | None = None,
        from_executed_at: int | None = None,
        to_executed_at: int | None = None,
    ) -> list[Transaction]:
        if not portfolios_repository.find_by_id(portfolio_id):
            raise NotFoundError("Portfolio", portfolio_id)
        return transactions_repository.list_by_portfolio(
            portfolio_id,
            type_=type_,
            security_id=security_id,
            investment_case_id=investment_case_id,
            account_id=account_id,
            from_executed_at=from_executed_at,
            to_executed_at=to_executed_at,
        )

    def list_by_security(self, security_id: str) -> list[Transaction]:
        if not securities_repository.find_by_id(security_id):
            raise NotFoundError("Security", security_id)
        return transactions_repository.list_by_security(security_id)

    def list_by_investment_case(self, investment_case_id: str) -> list[Transaction]:
        if not investment_cases_repository.find_by_id(investment_case_id):
            raise NotFoundError("InvestmentCase", investment_case_id)
        return transactions_repository.list_by_investment_case(investment_case_id)

    def get_cash_balance_paise(self, portfolio_id: str) -> int:
        if not portfolios_repository.find_by_id(portfolio_id):
            raise NotFoundError("Portfolio", portfolio_id)
        return transactions_repository.sum_cash_balance_paise(portfolio_id)

    def create(self, input_: CreateTransactionInput) -> Transaction:
        if not portfolios_repository.find_by_id(input_.portfolio_id):
            raise NotFoundError("Portfolio", input_.portfolio_id)

        if input_.account_id:
            account = portfolio_accounts_repository.find_by_id(input_.account_id)
            if not account:
                raise NotFoundError("PortfolioAccount", input_.account_id)
            if account.portfolio_id != input_.portfolio_id:
                raise ValidationError(
                    "account_id does not belong to the given portfolio"
                )

        if input_.security_id and not securities_repository.find_by_id(
            input_.security_id
        ):
            raise NotFoundError("Security", input_.security_id)

        if input_.investment_case_id:
            case = investment_cases_repository.find_by_id(input_.investment_case_id)
            if not case:
                raise NotFoundError("InvestmentCase", input_.investment_case_id)
            if case.portfolio_id != input_.portfolio_id:
                raise ValidationError(
                    "investment_case_id does not belong to the given portfolio"
                )
            if input_.security_id and case.security_id != input_.security_id:
                raise ValidationError(
                    "investment_case_id does not match security_id"
                )

        if input_.type in SECURITY_REQUIRED:
            if not input_.security_id:
                raise ValidationError(
                    f"security_id is required for {input_.type} transactions"
                )
            if input_.quantity_micros is None or input_.quantity_micros <= 0:
                raise ValidationError(
                    f"quantity_micros must be positive for {input_.type} transactions"
                )

        if input_.type in PRICE_REQUIRED:
            if input_.price_paise is None:
                raise ValidationError(
                    f"price_paise is required for {input_.type} transactions"
                )
            if input_.price_paise < 0:
                raise ValidationError("price_paise must be non-negative")

        fees = input_.fees_paise
        taxes = input_.taxes_paise
        if fees < 0:
            raise ValidationError("fees_paise must be non-negative")
        if taxes < 0:
            raise ValidationError("taxes_paise must be non-negative")
        if input_.exchange_rate_micros <= 0:
            raise ValidationError("exchange_rate_micros must be positive")

        gross = (
            input_.gross_amount_paise
            if input_.gross_amount_paise is not None
            else compute_gross_amount_paise(
                input_.quantity_micros, input_.price_paise
            )
        )

        if input_.type in CASH_AMOUNT_REQUIRED and (gross is None or gross < 0):
            raise ValidationError(
                f"gross_amount_paise is required for {input_.type} transactions"
            )

        net = input_.net_amount_paise
        if net is None and gross is not None:
            net = compute_net_cash_magnitude(
                type_=input_.type,
                gross_amount_paise=gross,
                fees_paise=fees,
                taxes_paise=taxes,
            )

        cash_effect = (
            input_.cash_effect_paise
            if input_.cash_effect_paise is not None
            else compute_cash_effect_paise(
                type_=input_.type,
                gross_amount_paise=gross,
                fees_paise=fees,
                taxes_paise=taxes,
            )
        )

        return transactions_repository.create(
            CreateTransactionInput(
                id=input_.id,
                portfolio_id=input_.portfolio_id,
                account_id=input_.account_id,
                security_id=input_.security_id,
                investment_case_id=input_.investment_case_id,
                type=input_.type,
                quantity_micros=input_.quantity_micros,
                price_paise=input_.price_paise,
                gross_amount_paise=gross,
                fees_paise=fees,
                taxes_paise=taxes,
                net_amount_paise=net,
                currency=(input_.currency or "INR").strip().upper(),
                exchange_rate_micros=input_.exchange_rate_micros,
                executed_at=input_.executed_at,
                settlement_date=input_.settlement_date,
                external_reference=(input_.external_reference or "").strip() or None,
                notes=(input_.notes or "").strip() or None,
            ),
            cash_effect_paise=cash_effect,
        )

    def delete(self, id_: str) -> None:
        self.get_by_id(id_)
        transactions_repository.delete(id_)


class MarketPricesService:
    def get(self, security_id: str, price_date: str) -> MarketPrice:
        price = market_prices_repository.find(security_id, price_date)
        if not price:
            raise NotFoundError(
                "MarketPrice", f"{security_id}:{price_date}"
            )
        return price

    def list_by_security(
        self, security_id: str, *, limit: int = 500
    ) -> list[MarketPrice]:
        if not securities_repository.find_by_id(security_id):
            raise NotFoundError("Security", security_id)
        return market_prices_repository.list_by_security(security_id, limit=limit)

    def latest(self, security_id: str) -> MarketPrice | None:
        if not securities_repository.find_by_id(security_id):
            raise NotFoundError("Security", security_id)
        return market_prices_repository.latest(security_id)

    def upsert(self, input_: UpsertMarketPriceInput) -> MarketPrice:
        if not securities_repository.find_by_id(input_.security_id):
            raise NotFoundError("Security", input_.security_id)
        if not _DATE_RE.match(input_.price_date):
            raise ValidationError("price_date must be YYYY-MM-DD")
        if input_.price_paise < 0:
            raise ValidationError("price_paise must be non-negative")
        return market_prices_repository.upsert(
            UpsertMarketPriceInput(
                security_id=input_.security_id,
                price_date=input_.price_date,
                price_paise=input_.price_paise,
                currency=(input_.currency or "INR").strip().upper(),
                source=(input_.source or "").strip() or None,
                captured_at=input_.captured_at,
            )
        )

    def delete(self, security_id: str, price_date: str) -> None:
        self.get(security_id, price_date)
        market_prices_repository.delete(security_id, price_date)


transactions_service = TransactionsService()
market_prices_service = MarketPricesService()

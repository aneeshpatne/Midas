"""Portfolios and portfolio accounts services."""

from __future__ import annotations

from midas.db.errors import NotFoundError, ValidationError
from midas.db.models import (
    CreatePortfolioAccountInput,
    CreatePortfolioInput,
    Portfolio,
    PortfolioAccount,
    PortfolioCashSummary,
    UpdatePortfolioAccountInput,
    UpdatePortfolioInput,
)
from midas.db.repositories.portfolios import (
    portfolio_accounts_repository,
    portfolios_repository,
)
from midas.db.repositories.transactions import transactions_repository


class PortfoliosService:
    def get_by_id(self, id_: str) -> Portfolio:
        portfolio = portfolios_repository.find_by_id(id_)
        if not portfolio:
            raise NotFoundError("Portfolio", id_)
        return portfolio

    def list(self, *, include_archived: bool = False) -> list[Portfolio]:
        return portfolios_repository.list(include_archived=include_archived)

    def create(self, input_: CreatePortfolioInput) -> Portfolio:
        if not input_.name.strip():
            raise ValidationError("name is required")
        if (
            input_.target_capital_paise is not None
            and input_.target_capital_paise < 0
        ):
            raise ValidationError("target_capital_paise must be non-negative")
        return portfolios_repository.create(
            CreatePortfolioInput(
                id=input_.id,
                name=input_.name.strip(),
                description=(input_.description or "").strip() or None,
                strategy=(input_.strategy or "").strip() or None,
                base_currency=(input_.base_currency or "INR").strip().upper(),
                target_capital_paise=input_.target_capital_paise,
            )
        )

    def update(self, id_: str, input_: UpdatePortfolioInput) -> Portfolio:
        self.get_by_id(id_)
        patch = input_.model_dump(exclude_unset=True)
        if "name" in patch:
            name = (patch["name"] or "").strip()
            if not name:
                raise ValidationError("name is required")
            patch["name"] = name
        if "description" in patch:
            patch["description"] = (patch["description"] or "").strip() or None
        if "strategy" in patch:
            patch["strategy"] = (patch["strategy"] or "").strip() or None
        if "base_currency" in patch:
            cur = (patch["base_currency"] or "").strip().upper()
            if not cur:
                raise ValidationError("base_currency is required")
            patch["base_currency"] = cur
        if (
            "target_capital_paise" in patch
            and patch["target_capital_paise"] is not None
            and patch["target_capital_paise"] < 0
        ):
            raise ValidationError("target_capital_paise must be non-negative")
        updated = portfolios_repository.update(id_, UpdatePortfolioInput(**patch))
        if not updated:
            raise NotFoundError("Portfolio", id_)
        return updated

    def archive(self, id_: str) -> Portfolio:
        self.get_by_id(id_)
        archived = portfolios_repository.archive(id_)
        if not archived:
            raise NotFoundError("Portfolio", id_)
        return archived

    def unarchive(self, id_: str) -> Portfolio:
        self.get_by_id(id_)
        unarchived = portfolios_repository.unarchive(id_)
        if not unarchived:
            raise NotFoundError("Portfolio", id_)
        return unarchived

    def get_cash_summary(self, portfolio_id: str) -> PortfolioCashSummary:
        portfolio = self.get_by_id(portfolio_id)
        cash_balance = transactions_repository.sum_cash_balance_paise(portfolio_id)
        deposits = transactions_repository.sum_deposits_paise(portfolio_id)
        withdrawals = transactions_repository.sum_withdrawals_paise(portfolio_id)
        net = transactions_repository.sum_net_contributed_capital_paise(portfolio_id)
        remaining = (
            None
            if portfolio.target_capital_paise is None
            else portfolio.target_capital_paise - net
        )
        return PortfolioCashSummary(
            portfolio_id=portfolio_id,
            cash_balance_paise=cash_balance,
            total_deposits_paise=deposits,
            total_withdrawals_paise=withdrawals,
            net_contributed_capital_paise=net,
            target_capital_paise=portfolio.target_capital_paise,
            remaining_to_contribute_paise=remaining,
        )

    def delete(self, id_: str) -> None:
        self.get_by_id(id_)
        portfolios_repository.delete(id_)


class PortfolioAccountsService:
    def get_by_id(self, id_: str) -> PortfolioAccount:
        account = portfolio_accounts_repository.find_by_id(id_)
        if not account:
            raise NotFoundError("PortfolioAccount", id_)
        return account

    def list_by_portfolio(self, portfolio_id: str) -> list[PortfolioAccount]:
        if not portfolios_repository.find_by_id(portfolio_id):
            raise NotFoundError("Portfolio", portfolio_id)
        return portfolio_accounts_repository.list_by_portfolio(portfolio_id)

    def create(self, input_: CreatePortfolioAccountInput) -> PortfolioAccount:
        if not portfolios_repository.find_by_id(input_.portfolio_id):
            raise NotFoundError("Portfolio", input_.portfolio_id)
        if not input_.name.strip():
            raise ValidationError("name is required")
        return portfolio_accounts_repository.create(
            CreatePortfolioAccountInput(
                id=input_.id,
                portfolio_id=input_.portfolio_id,
                name=input_.name.strip(),
                institution=(input_.institution or "").strip() or None,
                account_reference=(input_.account_reference or "").strip() or None,
                currency=(input_.currency or "INR").strip().upper(),
            )
        )

    def update(
        self, id_: str, input_: UpdatePortfolioAccountInput
    ) -> PortfolioAccount:
        self.get_by_id(id_)
        patch = input_.model_dump(exclude_unset=True)
        if "name" in patch:
            name = (patch["name"] or "").strip()
            if not name:
                raise ValidationError("name is required")
            patch["name"] = name
        if "institution" in patch:
            patch["institution"] = (patch["institution"] or "").strip() or None
        if "account_reference" in patch:
            patch["account_reference"] = (
                (patch["account_reference"] or "").strip() or None
            )
        if "currency" in patch:
            cur = (patch["currency"] or "").strip().upper()
            if not cur:
                raise ValidationError("currency is required")
            patch["currency"] = cur
        updated = portfolio_accounts_repository.update(
            id_, UpdatePortfolioAccountInput(**patch)
        )
        if not updated:
            raise NotFoundError("PortfolioAccount", id_)
        return updated

    def delete(self, id_: str) -> None:
        self.get_by_id(id_)
        portfolio_accounts_repository.delete(id_)


portfolios_service = PortfoliosService()
portfolio_accounts_service = PortfolioAccountsService()

"""Securities service."""

from __future__ import annotations

from midas.db.errors import NotFoundError, ValidationError
from midas.db.models import (
    CreateSecurityInput,
    Security,
    SecurityWithCompany,
    UpdateSecurityInput,
)
from midas.db.repositories.companies import companies_repository
from midas.db.repositories.securities import securities_repository


def _norm_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def _norm_exchange(exchange: str) -> str:
    return exchange.strip().upper()


def _with_company(security: Security) -> SecurityWithCompany:
    company = (
        companies_repository.find_by_id(security.company_id)
        if security.company_id
        else None
    )
    return SecurityWithCompany(**security.model_dump(), company=company)


class SecuritiesService:
    def get_by_id(self, id_: str) -> Security:
        security = securities_repository.find_by_id(id_)
        if not security:
            raise NotFoundError("Security", id_)
        return security

    def get_by_id_with_company(self, id_: str) -> SecurityWithCompany:
        return _with_company(self.get_by_id(id_))

    def get_by_exchange_ticker(
        self, exchange: str, ticker: str
    ) -> Security | None:
        return securities_repository.find_by_exchange_ticker(
            _norm_exchange(exchange), _norm_ticker(ticker)
        )

    def list(
        self, *, active_only: bool = False, company_id: str | None = None
    ) -> list[Security]:
        return securities_repository.list(
            active_only=active_only, company_id=company_id
        )

    def list_with_company(
        self, *, active_only: bool = False, company_id: str | None = None
    ) -> list[SecurityWithCompany]:
        return [
            _with_company(s)
            for s in self.list(active_only=active_only, company_id=company_id)
        ]

    def create(self, input_: CreateSecurityInput) -> Security:
        ticker = _norm_ticker(input_.ticker)
        exchange = _norm_exchange(input_.exchange)
        if not ticker:
            raise ValidationError("ticker is required")
        if not exchange:
            raise ValidationError("exchange is required")
        if not input_.name.strip():
            raise ValidationError("name is required")
        if not input_.currency.strip():
            raise ValidationError("currency is required")
        if input_.company_id and not companies_repository.find_by_id(
            input_.company_id
        ):
            raise NotFoundError("Company", input_.company_id)
        existing = securities_repository.find_by_exchange_ticker(exchange, ticker)
        if existing:
            raise ValidationError(
                f"Security already exists for {exchange}:{ticker}"
            )
        return securities_repository.create(
            CreateSecurityInput(
                id=input_.id,
                company_id=input_.company_id,
                ticker=ticker,
                exchange=exchange,
                name=input_.name.strip(),
                security_type=input_.security_type,
                currency=input_.currency.strip().upper(),
                isin=(input_.isin or "").strip() or None,
                is_active=input_.is_active,
            )
        )

    def update(self, id_: str, input_: UpdateSecurityInput) -> Security:
        current = self.get_by_id(id_)
        patch = input_.model_dump(exclude_unset=True)
        if "ticker" in patch:
            t = _norm_ticker(patch["ticker"] or "")
            if not t:
                raise ValidationError("ticker is required")
            patch["ticker"] = t
        if "exchange" in patch:
            e = _norm_exchange(patch["exchange"] or "")
            if not e:
                raise ValidationError("exchange is required")
            patch["exchange"] = e
        if "name" in patch:
            name = (patch["name"] or "").strip()
            if not name:
                raise ValidationError("name is required")
            patch["name"] = name
        if "currency" in patch:
            cur = (patch["currency"] or "").strip().upper()
            if not cur:
                raise ValidationError("currency is required")
            patch["currency"] = cur
        if "isin" in patch:
            patch["isin"] = (patch["isin"] or "").strip() or None
        if patch.get("company_id"):
            if not companies_repository.find_by_id(patch["company_id"]):
                raise NotFoundError("Company", patch["company_id"])
        next_exchange = patch.get("exchange", current.exchange)
        next_ticker = patch.get("ticker", current.ticker)
        conflict = securities_repository.find_by_exchange_ticker(
            next_exchange, next_ticker
        )
        if conflict and conflict.id != id_:
            raise ValidationError(
                f"Security already exists for {next_exchange}:{next_ticker}"
            )
        updated = securities_repository.update(id_, UpdateSecurityInput(**patch))
        if not updated:
            raise NotFoundError("Security", id_)
        return updated

    def link_company(self, security_id: str, company_id: str | None) -> Security:
        if company_id and not companies_repository.find_by_id(company_id):
            raise NotFoundError("Company", company_id)
        return self.update(
            security_id, UpdateSecurityInput(company_id=company_id)
        )

    def deactivate(self, id_: str) -> Security:
        return self.update(id_, UpdateSecurityInput(is_active=False))

    def activate(self, id_: str) -> Security:
        return self.update(id_, UpdateSecurityInput(is_active=True))

    def delete(self, id_: str) -> None:
        self.get_by_id(id_)
        securities_repository.delete(id_)


securities_service = SecuritiesService()

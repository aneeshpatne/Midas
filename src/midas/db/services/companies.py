"""Companies service."""

from __future__ import annotations

import re

from midas.db.errors import NotFoundError, ValidationError
from midas.db.models import (
    Company,
    CompanyStatsBucket,
    CreateCompanyInput,
    MarketCapBucket,
    Security,
    UpdateCompanyInput,
)
from midas.db.repositories.companies import companies_repository
from midas.db.repositories.securities import securities_repository

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CompaniesService:
    def get_by_id(self, id_: str) -> Company:
        company = companies_repository.find_by_id(id_)
        if not company:
            raise NotFoundError("Company", id_)
        return company

    def list(
        self,
        *,
        sector: str | None = None,
        industry: str | None = None,
        market_cap_bucket: MarketCapBucket | None = None,
        limit: int = 5000,
    ) -> list[Company]:
        return companies_repository.list(
            sector=sector,
            industry=industry,
            market_cap_bucket=market_cap_bucket,
            limit=limit,
        )

    def create(self, input_: CreateCompanyInput) -> Company:
        if not input_.name.strip():
            raise ValidationError("name is required")
        if input_.classification_as_of and not _DATE_RE.match(
            input_.classification_as_of
        ):
            raise ValidationError("classification_as_of must be YYYY-MM-DD")
        return companies_repository.create(
            CreateCompanyInput(
                id=input_.id,
                name=input_.name.strip(),
                legal_name=(input_.legal_name or "").strip() or None,
                sector=(input_.sector or "").strip() or None,
                industry=(input_.industry or "").strip() or None,
                market_cap_bucket=input_.market_cap_bucket,
                country_code=(input_.country_code or "IN").strip().upper(),
                website=(input_.website or "").strip() or None,
                classification_source=(
                    (input_.classification_source or "").strip() or None
                ),
                classification_as_of=(
                    (input_.classification_as_of or "").strip() or None
                ),
                notes=(input_.notes or "").strip() or None,
            )
        )

    def update(self, id_: str, input_: UpdateCompanyInput) -> Company:
        self.get_by_id(id_)
        patch = input_.model_dump(exclude_unset=True)
        if "name" in patch:
            name = (patch["name"] or "").strip()
            if not name:
                raise ValidationError("name is required")
            patch["name"] = name
        if "legal_name" in patch:
            patch["legal_name"] = (patch["legal_name"] or "").strip() or None
        if "sector" in patch:
            patch["sector"] = (patch["sector"] or "").strip() or None
        if "industry" in patch:
            patch["industry"] = (patch["industry"] or "").strip() or None
        if "country_code" in patch:
            code = (patch["country_code"] or "").strip().upper()
            if not code:
                raise ValidationError("country_code is required")
            patch["country_code"] = code
        if "website" in patch:
            patch["website"] = (patch["website"] or "").strip() or None
        if "classification_source" in patch:
            patch["classification_source"] = (
                (patch["classification_source"] or "").strip() or None
            )
        if "classification_as_of" in patch:
            as_of = (patch["classification_as_of"] or "").strip() or None
            if as_of and not _DATE_RE.match(as_of):
                raise ValidationError("classification_as_of must be YYYY-MM-DD")
            patch["classification_as_of"] = as_of
        if "notes" in patch:
            patch["notes"] = (patch["notes"] or "").strip() or None
        updated = companies_repository.update(id_, UpdateCompanyInput(**patch))
        if not updated:
            raise NotFoundError("Company", id_)
        return updated

    def delete(self, id_: str) -> None:
        self.get_by_id(id_)
        companies_repository.delete(id_)

    def list_securities(self, company_id: str) -> list[Security]:
        self.get_by_id(company_id)
        return securities_repository.list_by_company(company_id)

    def stats(self) -> dict[str, list[CompanyStatsBucket]]:
        return {
            "by_sector": companies_repository.count_by_sector(),
            "by_industry": companies_repository.count_by_industry(),
            "by_market_cap_bucket": companies_repository.count_by_market_cap_bucket(),
        }


companies_service = CompaniesService()

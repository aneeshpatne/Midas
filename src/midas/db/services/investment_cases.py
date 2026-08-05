"""Investment cases and thesis revisions services."""

from __future__ import annotations

from midas.db.errors import NotFoundError, ValidationError
from midas.db.models import (
    CreateInvestmentCaseInput,
    CreateThesisRevisionInput,
    InvestmentCase,
    InvestmentCaseStatus,
    ThesisRevision,
    UpdateInvestmentCaseInput,
)
from midas.db.repositories.investment_cases import (
    investment_cases_repository,
    thesis_revisions_repository,
)
from midas.db.repositories.portfolios import portfolios_repository
from midas.db.repositories.securities import securities_repository


class InvestmentCasesService:
    def get_by_id(self, id_: str) -> InvestmentCase:
        case = investment_cases_repository.find_by_id(id_)
        if not case:
            raise NotFoundError("InvestmentCase", id_)
        return case

    def list_by_portfolio(
        self,
        portfolio_id: str,
        *,
        status: InvestmentCaseStatus | None = None,
    ) -> list[InvestmentCase]:
        if not portfolios_repository.find_by_id(portfolio_id):
            raise NotFoundError("Portfolio", portfolio_id)
        return investment_cases_repository.list_by_portfolio(
            portfolio_id, status=status
        )

    def list_by_security(self, security_id: str) -> list[InvestmentCase]:
        if not securities_repository.find_by_id(security_id):
            raise NotFoundError("Security", security_id)
        return investment_cases_repository.list_by_security(security_id)

    def create(self, input_: CreateInvestmentCaseInput) -> InvestmentCase:
        if not portfolios_repository.find_by_id(input_.portfolio_id):
            raise NotFoundError("Portfolio", input_.portfolio_id)
        if not securities_repository.find_by_id(input_.security_id):
            raise NotFoundError("Security", input_.security_id)
        if not input_.name.strip():
            raise ValidationError("name is required")
        if (
            input_.time_horizon_months is not None
            and input_.time_horizon_months <= 0
        ):
            raise ValidationError("time_horizon_months must be positive")
        if input_.conviction is not None and not (1 <= input_.conviction <= 5):
            raise ValidationError("conviction must be between 1 and 5")
        return investment_cases_repository.create(
            CreateInvestmentCaseInput(
                id=input_.id,
                portfolio_id=input_.portfolio_id,
                security_id=input_.security_id,
                name=input_.name.strip(),
                status=input_.status,
                conviction=input_.conviction,
                time_horizon_months=input_.time_horizon_months,
                opened_at=input_.opened_at,
                closed_at=input_.closed_at,
            )
        )

    def update(self, id_: str, input_: UpdateInvestmentCaseInput) -> InvestmentCase:
        self.get_by_id(id_)
        patch = input_.model_dump(exclude_unset=True)
        if "name" in patch:
            name = (patch["name"] or "").strip()
            if not name:
                raise ValidationError("name is required")
            patch["name"] = name
        if (
            "time_horizon_months" in patch
            and patch["time_horizon_months"] is not None
            and patch["time_horizon_months"] <= 0
        ):
            raise ValidationError("time_horizon_months must be positive")
        if (
            "conviction" in patch
            and patch["conviction"] is not None
            and not (1 <= patch["conviction"] <= 5)
        ):
            raise ValidationError("conviction must be between 1 and 5")
        updated = investment_cases_repository.update(
            id_, UpdateInvestmentCaseInput(**patch)
        )
        if not updated:
            raise NotFoundError("InvestmentCase", id_)
        return updated

    def delete(self, id_: str) -> None:
        self.get_by_id(id_)
        investment_cases_repository.delete(id_)


class ThesisRevisionsService:
    def get_by_id(self, id_: str) -> ThesisRevision:
        rev = thesis_revisions_repository.find_by_id(id_)
        if not rev:
            raise NotFoundError("ThesisRevision", id_)
        return rev

    def list_by_case(self, investment_case_id: str) -> list[ThesisRevision]:
        if not investment_cases_repository.find_by_id(investment_case_id):
            raise NotFoundError("InvestmentCase", investment_case_id)
        return thesis_revisions_repository.list_by_case(investment_case_id)

    def create(self, input_: CreateThesisRevisionInput) -> ThesisRevision:
        if not investment_cases_repository.find_by_id(input_.investment_case_id):
            raise NotFoundError("InvestmentCase", input_.investment_case_id)
        if not input_.thesis.strip():
            raise ValidationError("thesis is required")
        if (
            input_.target_price_paise is not None
            and input_.target_price_paise < 0
        ):
            raise ValidationError("target_price_paise must be non-negative")
        if input_.conviction is not None and not (1 <= input_.conviction <= 5):
            raise ValidationError("conviction must be between 1 and 5")
        rev_no = thesis_revisions_repository.next_revision_number(
            input_.investment_case_id
        )
        return thesis_revisions_repository.create(
            CreateThesisRevisionInput(
                id=input_.id,
                investment_case_id=input_.investment_case_id,
                revision_type=input_.revision_type if rev_no > 1 else "INITIAL",
                thesis=input_.thesis.strip(),
                bull_case=(input_.bull_case or "").strip() or None,
                base_case=(input_.base_case or "").strip() or None,
                bear_case=(input_.bear_case or "").strip() or None,
                catalysts=(input_.catalysts or "").strip() or None,
                risks=(input_.risks or "").strip() or None,
                invalidation_conditions=(
                    (input_.invalidation_conditions or "").strip() or None
                ),
                target_price_paise=input_.target_price_paise,
                conviction=input_.conviction,
                effective_at=input_.effective_at,
            ),
            revision_number=rev_no,
        )

    def delete(self, id_: str) -> None:
        self.get_by_id(id_)
        thesis_revisions_repository.delete(id_)


investment_cases_service = InvestmentCasesService()
thesis_revisions_service = ThesisRevisionsService()

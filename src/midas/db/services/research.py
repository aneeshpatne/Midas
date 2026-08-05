"""Research runs service (DB-backed diligence artifacts)."""

from __future__ import annotations

import json
import re

from midas.db.errors import NotFoundError, ValidationError
from midas.db.helpers import now_ms
from midas.db.models import (
    AddResearchRunSecurityInput,
    AppendResearchEvidenceInput,
    CreateResearchPortfolioLinkInput,
    CreateResearchRunInput,
    ResearchEvidence,
    ResearchPortfolioLink,
    ResearchRun,
    ResearchRunBundle,
    ResearchRunSecurity,
    ResearchRunStatus,
    ResearchWorkflow,
    UpdateResearchRunInput,
)
from midas.db.repositories.investment_cases import investment_cases_repository
from midas.db.repositories.portfolios import portfolios_repository
from midas.db.repositories.research import (
    research_evidence_repository,
    research_portfolio_links_repository,
    research_run_securities_repository,
    research_runs_repository,
)
from midas.db.repositories.securities import securities_repository

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ResearchRunsService:
    def get_by_id(self, id_: str) -> ResearchRun:
        run = research_runs_repository.find_by_id(id_)
        if not run:
            raise NotFoundError("ResearchRun", id_)
        return run

    def get_bundle(self, id_: str) -> ResearchRunBundle:
        run = self.get_by_id(id_)
        return ResearchRunBundle(
            run=run,
            securities=research_run_securities_repository.list_by_run(id_),
            evidence=research_evidence_repository.list_by_run(id_),
            portfolio_links=research_portfolio_links_repository.list_by_run(id_),
        )

    def list(
        self,
        *,
        slug: str | None = None,
        status: ResearchRunStatus | None = None,
        workflow: ResearchWorkflow | None = None,
        limit: int = 100,
    ) -> list[ResearchRun]:
        return research_runs_repository.list(
            slug=slug, status=status, workflow=workflow, limit=limit
        )

    def create(self, input_: CreateResearchRunInput) -> ResearchRun:
        slug = input_.slug.strip().lower()
        if not _SLUG_RE.match(slug):
            raise ValidationError(
                "slug must be lowercase kebab-case (e.g. nifty100-7y)"
            )
        if not input_.universe_or_company.strip():
            raise ValidationError("universe_or_company is required")
        if not input_.horizon_text.strip():
            raise ValidationError(
                "horizon_text is required; do not assume a horizon"
            )
        if input_.horizon_months is not None and input_.horizon_months <= 0:
            raise ValidationError("horizon_months must be positive")
        return research_runs_repository.create(
            CreateResearchRunInput(
                id=input_.id,
                slug=slug,
                run_key=input_.run_key,
                workflow=input_.workflow,
                status=input_.status,
                title=(input_.title or "").strip() or None,
                universe_or_company=input_.universe_or_company.strip(),
                horizon_text=input_.horizon_text.strip(),
                horizon_months=input_.horizon_months,
                cutoff_at=input_.cutoff_at if input_.cutoff_at is not None else now_ms(),
                mandate_md=input_.mandate_md,
                report_md=input_.report_md,
                primary_runtime=input_.primary_runtime,
                execution_mode=input_.execution_mode,
            )
        )

    def update(self, id_: str, input_: UpdateResearchRunInput) -> ResearchRun:
        self.get_by_id(id_)
        patch = input_.model_dump(exclude_unset=True)
        if "universe_or_company" in patch and not (
            patch["universe_or_company"] or ""
        ).strip():
            raise ValidationError("universe_or_company is required")
        if "horizon_text" in patch and not (patch["horizon_text"] or "").strip():
            raise ValidationError("horizon_text is required")
        if (
            "horizon_months" in patch
            and patch["horizon_months"] is not None
            and patch["horizon_months"] <= 0
        ):
            raise ValidationError("horizon_months must be positive")
        if "universe_or_company" in patch:
            patch["universe_or_company"] = patch["universe_or_company"].strip()
        if "horizon_text" in patch:
            patch["horizon_text"] = patch["horizon_text"].strip()
        if "title" in patch:
            patch["title"] = (patch["title"] or "").strip() or None
        updated = research_runs_repository.update(
            id_, UpdateResearchRunInput(**patch)
        )
        if not updated:
            raise NotFoundError("ResearchRun", id_)
        return updated

    def set_status(self, id_: str, status: ResearchRunStatus) -> ResearchRun:
        return self.update(id_, UpdateResearchRunInput(status=status))

    def set_mandate(self, id_: str, mandate_md: str) -> ResearchRun:
        if not mandate_md.strip():
            raise ValidationError("mandate_md is required")
        return self.update(id_, UpdateResearchRunInput(mandate_md=mandate_md))

    def set_report(self, id_: str, report_md: str) -> ResearchRun:
        if not report_md.strip():
            raise ValidationError("report_md is required")
        return self.update(id_, UpdateResearchRunInput(report_md=report_md))

    def complete(self, id_: str, report_md: str | None = None) -> ResearchRun:
        run = self.get_by_id(id_)
        if not (run.mandate_md or "").strip():
            raise ValidationError(
                "cannot complete research run without mandate_md"
            )
        report = report_md if report_md is not None else run.report_md
        if not (report or "").strip():
            raise ValidationError(
                "cannot complete research run without report_md"
            )
        return self.update(
            id_,
            UpdateResearchRunInput(report_md=report, status="COMPLETED"),
        )

    def add_security(
        self, input_: AddResearchRunSecurityInput
    ) -> ResearchRunSecurity:
        self.get_by_id(input_.research_run_id)
        if not input_.symbol.strip():
            raise ValidationError("symbol is required")
        if input_.security_id and not securities_repository.find_by_id(
            input_.security_id
        ):
            raise NotFoundError("Security", input_.security_id)
        return research_run_securities_repository.add(
            AddResearchRunSecurityInput(
                id=input_.id,
                research_run_id=input_.research_run_id,
                security_id=input_.security_id,
                symbol=input_.symbol.strip().upper(),
                exchange=(input_.exchange or "").strip().upper() or None,
                role=input_.role,
                sort_order=input_.sort_order,
                notes=(input_.notes or "").strip() or None,
            )
        )

    def list_securities(self, research_run_id: str) -> list[ResearchRunSecurity]:
        self.get_by_id(research_run_id)
        return research_run_securities_repository.list_by_run(research_run_id)

    def remove_security(self, id_: str) -> None:
        row = research_run_securities_repository.find_by_id(id_)
        if not row:
            raise NotFoundError("ResearchRunSecurity", id_)
        research_run_securities_repository.delete(id_)

    def append_evidence(
        self, input_: AppendResearchEvidenceInput
    ) -> ResearchEvidence:
        self.get_by_id(input_.research_run_id)
        if not input_.record_type.strip():
            raise ValidationError("record_type is required")
        if input_.security_id and not securities_repository.find_by_id(
            input_.security_id
        ):
            raise NotFoundError("Security", input_.security_id)
        try:
            payload_json = json.dumps(input_.payload, default=str)
        except TypeError as exc:
            raise ValidationError("payload must be JSON-serializable") from exc
        seq = research_evidence_repository.next_seq(input_.research_run_id)
        return research_evidence_repository.append(
            AppendResearchEvidenceInput(
                id=input_.id,
                research_run_id=input_.research_run_id,
                record_type=input_.record_type.strip(),
                record_id=(input_.record_id or "").strip() or None,
                payload=input_.payload,
                as_of=input_.as_of,
                security_id=input_.security_id,
                symbol=(input_.symbol or "").strip().upper() or None,
            ),
            seq=seq,
            payload_json=payload_json,
        )

    def list_evidence(
        self,
        research_run_id: str,
        *,
        record_type: str | None = None,
        symbol: str | None = None,
        from_seq: int | None = None,
        limit: int = 10_000,
    ) -> list[ResearchEvidence]:
        self.get_by_id(research_run_id)
        return research_evidence_repository.list_by_run(
            research_run_id,
            record_type=record_type,
            symbol=symbol,
            from_seq=from_seq,
            limit=limit,
        )

    def link_to_portfolio(
        self, input_: CreateResearchPortfolioLinkInput
    ) -> ResearchPortfolioLink:
        self.get_by_id(input_.research_run_id)
        if not portfolios_repository.find_by_id(input_.portfolio_id):
            raise NotFoundError("Portfolio", input_.portfolio_id)
        if input_.investment_case_id:
            case = investment_cases_repository.find_by_id(
                input_.investment_case_id
            )
            if not case:
                raise NotFoundError("InvestmentCase", input_.investment_case_id)
            if case.portfolio_id != input_.portfolio_id:
                raise ValidationError(
                    "investment_case_id does not belong to the given portfolio"
                )
        return research_portfolio_links_repository.create(
            CreateResearchPortfolioLinkInput(
                id=input_.id,
                research_run_id=input_.research_run_id,
                portfolio_id=input_.portfolio_id,
                investment_case_id=input_.investment_case_id,
                link_role=input_.link_role,
                notes=(input_.notes or "").strip() or None,
            )
        )

    def list_portfolio_links(
        self, research_run_id: str
    ) -> list[ResearchPortfolioLink]:
        self.get_by_id(research_run_id)
        return research_portfolio_links_repository.list_by_run(research_run_id)

    def list_links_by_portfolio(
        self, portfolio_id: str
    ) -> list[ResearchPortfolioLink]:
        if not portfolios_repository.find_by_id(portfolio_id):
            raise NotFoundError("Portfolio", portfolio_id)
        return research_portfolio_links_repository.list_by_portfolio(portfolio_id)

    def list_links_by_investment_case(
        self, investment_case_id: str
    ) -> list[ResearchPortfolioLink]:
        if not investment_cases_repository.find_by_id(investment_case_id):
            raise NotFoundError("InvestmentCase", investment_case_id)
        return research_portfolio_links_repository.list_by_investment_case(
            investment_case_id
        )

    def unlink_from_portfolio(self, link_id: str) -> None:
        link = research_portfolio_links_repository.find_by_id(link_id)
        if not link:
            raise NotFoundError("ResearchPortfolioLink", link_id)
        research_portfolio_links_repository.delete(link_id)

    def delete(self, id_: str) -> None:
        self.get_by_id(id_)
        research_runs_repository.delete(id_)


research_runs_service = ResearchRunsService()

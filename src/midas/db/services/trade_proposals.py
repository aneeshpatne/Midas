"""Approval-gated paper trade proposals."""

from __future__ import annotations

import json

from midas.db.errors import NotFoundError, ValidationError
from midas.db.helpers import now_ms
from midas.db.models import (
    CreateTradeProposalInput,
    CreateTransactionInput,
    ProposedTrade,
    TradeProposal,
    TradeProposalStatus,
    TradeProposalView,
    Transaction,
)
from midas.db.repositories.base import conn
from midas.db.repositories.portfolios import portfolios_repository
from midas.db.repositories.securities import securities_repository
from midas.db.repositories.trade_proposals import trade_proposals_repository
from midas.db.repositories.transactions import transactions_repository
from midas.db.services.transactions import transactions_service


def _view(row: TradeProposal) -> TradeProposalView:
    trades_raw = json.loads(row.trades_json)
    warnings_raw = json.loads(row.warnings_json)
    return TradeProposalView(
        id=row.id,
        portfolio_id=row.portfolio_id,
        status=row.status,
        trades=[ProposedTrade.model_validate(t) for t in trades_raw],
        warnings=[str(w) for w in warnings_raw],
        rationale=row.rationale,
        price_as_of=row.price_as_of,
        expires_at=row.expires_at,
        approved_at=row.approved_at,
        rejected_at=row.rejected_at,
        superseded_at=row.superseded_at,
        executed_at=row.executed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class TradeProposalsService:
    def get_by_id(self, id_: str) -> TradeProposalView:
        row = trade_proposals_repository.find_by_id(id_)
        if not row:
            raise NotFoundError("TradeProposal", id_)
        return _view(row)

    def list_by_portfolio(
        self,
        portfolio_id: str,
        status: TradeProposalStatus | None = None,
    ) -> list[TradeProposalView]:
        if not portfolios_repository.find_by_id(portfolio_id):
            raise NotFoundError("Portfolio", portfolio_id)
        return [
            _view(row)
            for row in trade_proposals_repository.list_by_portfolio(
                portfolio_id, status
            )
        ]

    def create(self, input_: CreateTradeProposalInput) -> TradeProposalView:
        if not portfolios_repository.find_by_id(input_.portfolio_id):
            raise NotFoundError("Portfolio", input_.portfolio_id)
        if not input_.trades:
            raise ValidationError("A proposal must contain at least one trade")
        if (
            input_.expires_at is not None
            and input_.expires_at <= input_.price_as_of
        ):
            raise ValidationError("expires_at must be after price_as_of")
        for trade in input_.trades:
            if not securities_repository.find_by_id(trade.security_id):
                raise NotFoundError("Security", trade.security_id)
            if trade.quantity_micros <= 0 or trade.quantity_micros % 1_000_000 != 0:
                raise ValidationError(
                    "Proposed trades require positive whole-share quantities"
                )
            if trade.price_paise < 0 or trade.fees_paise < 0 or trade.taxes_paise < 0:
                raise ValidationError("Prices, fees, and taxes must be non-negative")
        rationale = (input_.rationale or "").strip() or None
        return _view(
            trade_proposals_repository.create(
                CreateTradeProposalInput(
                    id=input_.id,
                    portfolio_id=input_.portfolio_id,
                    trades=input_.trades,
                    rationale=rationale,
                    warnings=input_.warnings,
                    price_as_of=input_.price_as_of,
                    expires_at=input_.expires_at,
                )
            )
        )

    def approve(
        self, id_: str, approved_at: int | None = None
    ) -> TradeProposalView:
        at = approved_at if approved_at is not None else now_ms()
        proposal = self.get_by_id(id_)
        if proposal.status != "DRAFT":
            raise ValidationError(
                f"Only DRAFT proposals can be approved; status is {proposal.status}"
            )
        if proposal.expires_at is not None and at > proposal.expires_at:
            raise ValidationError("Proposal has expired")
        if not trade_proposals_repository.set_status(
            id_, "DRAFT", "APPROVED", at
        ):
            raise ValidationError("Proposal status changed concurrently")
        return self.get_by_id(id_)

    def reject(
        self, id_: str, rejected_at: int | None = None
    ) -> TradeProposalView:
        return self._close_draft(
            id_, "REJECTED", rejected_at if rejected_at is not None else now_ms()
        )

    def supersede(
        self, id_: str, superseded_at: int | None = None
    ) -> TradeProposalView:
        return self._close_draft(
            id_,
            "SUPERSEDED",
            superseded_at if superseded_at is not None else now_ms(),
        )

    def _close_draft(
        self, id_: str, status: TradeProposalStatus, at: int
    ) -> TradeProposalView:
        proposal = self.get_by_id(id_)
        if proposal.status != "DRAFT":
            raise ValidationError(
                f"Only DRAFT proposals can be {status.lower()}; "
                f"status is {proposal.status}"
            )
        if not trade_proposals_repository.set_status(id_, "DRAFT", status, at):
            raise ValidationError("Proposal status changed concurrently")
        return self.get_by_id(id_)

    def execute(
        self, id_: str, executed_at: int
    ) -> dict[str, TradeProposalView | list[Transaction]]:
        c = conn()
        try:
            proposal = self.get_by_id(id_)
            if proposal.status != "APPROVED":
                raise ValidationError(
                    f"Proposal must be APPROVED; status is {proposal.status}"
                )
            if (
                proposal.expires_at is not None
                and executed_at > proposal.expires_at
            ):
                raise ValidationError(
                    "Approved proposal has expired; create a refreshed proposal"
                )
            existing = transactions_repository.list_by_portfolio(
                proposal.portfolio_id
            )
            if any(t.proposal_id == id_ for t in existing):
                raise ValidationError("Proposal already has recorded executions")

            transactions: list[Transaction] = []
            for trade in proposal.trades:
                transactions.append(
                    transactions_service.create_approved_trade(
                        CreateTransactionInput(
                            type=trade.type,
                            portfolio_id=proposal.portfolio_id,
                            security_id=trade.security_id,
                            account_id=trade.account_id,
                            investment_case_id=trade.investment_case_id,
                            quantity_micros=trade.quantity_micros,
                            price_paise=trade.price_paise,
                            fees_paise=trade.fees_paise,
                            taxes_paise=trade.taxes_paise,
                            currency=trade.currency or "INR",
                            settlement_date=trade.settlement_date,
                            notes=trade.notes,
                            executed_at=executed_at,
                            proposal_id=id_,
                        ),
                        commit=False,
                    )
                )
            if not trade_proposals_repository.set_status(
                id_, "APPROVED", "EXECUTED", executed_at, commit=False
            ):
                raise ValidationError("Proposal status changed concurrently")
            c.commit()
            return {"proposal": self.get_by_id(id_), "transactions": transactions}
        except Exception:
            c.rollback()
            raise


trade_proposals_service = TradeProposalsService()

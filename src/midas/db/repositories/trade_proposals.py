"""Trade proposals repository."""

from __future__ import annotations

import json

from midas.db.helpers import new_id, now_ms
from midas.db.models import (
    CreateTradeProposalInput,
    TradeProposal,
    TradeProposalStatus,
)
from midas.db.repositories.base import conn, fetchall_dicts, fetchone_dict

_STATUS_TIMESTAMP_COLUMN: dict[TradeProposalStatus, str] = {
    "APPROVED": "approved_at",
    "REJECTED": "rejected_at",
    "SUPERSEDED": "superseded_at",
    "EXECUTED": "executed_at",
}


class TradeProposalsRepository:
    def find_by_id(self, id_: str) -> TradeProposal | None:
        cur = conn().execute("SELECT * FROM trade_proposals WHERE id = ?", (id_,))
        row = fetchone_dict(cur)
        return TradeProposal.model_validate(row) if row else None

    def list_by_portfolio(
        self,
        portfolio_id: str,
        status: TradeProposalStatus | None = None,
    ) -> list[TradeProposal]:
        if status:
            cur = conn().execute(
                """
                SELECT * FROM trade_proposals
                WHERE portfolio_id = ? AND status = ?
                ORDER BY created_at DESC
                """,
                (portfolio_id, status),
            )
        else:
            cur = conn().execute(
                """
                SELECT * FROM trade_proposals
                WHERE portfolio_id = ?
                ORDER BY created_at DESC
                """,
                (portfolio_id,),
            )
        return [TradeProposal.model_validate(r) for r in fetchall_dicts(cur)]

    def create(
        self, input_: CreateTradeProposalInput, *, commit: bool = True
    ) -> TradeProposal:
        id_ = input_.id or new_id()
        ts = now_ms()
        trades_json = json.dumps(
            [t.model_dump(mode="json") for t in input_.trades],
            separators=(",", ":"),
        )
        warnings_json = json.dumps(input_.warnings or [], separators=(",", ":"))
        conn().execute(
            """
            INSERT INTO trade_proposals (
              id, portfolio_id, status, trades_json, rationale, warnings_json,
              price_as_of, expires_at, created_at, updated_at
            ) VALUES (?, ?, 'DRAFT', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_,
                input_.portfolio_id,
                trades_json,
                input_.rationale,
                warnings_json,
                input_.price_as_of,
                input_.expires_at,
                ts,
                ts,
            ),
        )
        if commit:
            conn().commit()
        created = self.find_by_id(id_)
        if not created:
            raise RuntimeError(f"Failed to create trade proposal: {id_}")
        return created

    def set_status(
        self,
        id_: str,
        from_status: TradeProposalStatus,
        to_status: TradeProposalStatus,
        timestamp: int,
        *,
        commit: bool = True,
    ) -> bool:
        column = _STATUS_TIMESTAMP_COLUMN.get(to_status)
        if not column:
            raise ValueError(f"Cannot set status timestamp for {to_status}")
        cur = conn().execute(
            f"""
            UPDATE trade_proposals
            SET status = ?, {column} = ?, updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (to_status, timestamp, timestamp, id_, from_status),
        )
        if commit:
            conn().commit()
        return cur.rowcount == 1


trade_proposals_repository = TradeProposalsRepository()

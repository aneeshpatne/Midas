"""Investment cases and thesis revisions repositories."""

from __future__ import annotations

from midas.db.helpers import new_id, now_ms
from midas.db.models import (
    CreateInvestmentCaseInput,
    CreateThesisRevisionInput,
    InvestmentCase,
    InvestmentCaseStatus,
    ThesisRevision,
    UpdateInvestmentCaseInput,
)
from midas.db.repositories.base import conn, fetchall_dicts, fetchone_dict


class InvestmentCasesRepository:
    def find_by_id(self, id_: str) -> InvestmentCase | None:
        cur = conn().execute(
            "SELECT * FROM investment_cases WHERE id = ?", (id_,)
        )
        row = fetchone_dict(cur)
        return InvestmentCase.model_validate(row) if row else None

    def list_by_portfolio(
        self,
        portfolio_id: str,
        *,
        status: InvestmentCaseStatus | None = None,
    ) -> list[InvestmentCase]:
        if status:
            cur = conn().execute(
                """
                SELECT * FROM investment_cases
                WHERE portfolio_id = ? AND status = ?
                ORDER BY updated_at DESC
                """,
                (portfolio_id, status),
            )
        else:
            cur = conn().execute(
                """
                SELECT * FROM investment_cases
                WHERE portfolio_id = ?
                ORDER BY updated_at DESC
                """,
                (portfolio_id,),
            )
        return [InvestmentCase.model_validate(r) for r in fetchall_dicts(cur)]

    def list_by_security(self, security_id: str) -> list[InvestmentCase]:
        cur = conn().execute(
            """
            SELECT * FROM investment_cases
            WHERE security_id = ?
            ORDER BY updated_at DESC
            """,
            (security_id,),
        )
        return [InvestmentCase.model_validate(r) for r in fetchall_dicts(cur)]

    def create(self, input_: CreateInvestmentCaseInput) -> InvestmentCase:
        id_ = input_.id or new_id()
        ts = now_ms()
        conn().execute(
            """
            INSERT INTO investment_cases (
              id, portfolio_id, security_id, name, status, conviction,
              time_horizon_months, opened_at, closed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_,
                input_.portfolio_id,
                input_.security_id,
                input_.name,
                input_.status,
                input_.conviction,
                input_.time_horizon_months,
                input_.opened_at,
                input_.closed_at,
                ts,
                ts,
            ),
        )
        conn().commit()
        created = self.find_by_id(id_)
        if not created:
            raise RuntimeError(f"Failed to create investment case: {id_}")
        return created

    def update(
        self, id_: str, input_: UpdateInvestmentCaseInput
    ) -> InvestmentCase | None:
        existing = self.find_by_id(id_)
        if not existing:
            return None
        data = existing.model_dump()
        data.update(input_.model_dump(exclude_unset=True))
        data["updated_at"] = now_ms()
        conn().execute(
            """
            UPDATE investment_cases SET
              name = ?, status = ?, conviction = ?, time_horizon_months = ?,
              opened_at = ?, closed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data["name"],
                data["status"],
                data["conviction"],
                data["time_horizon_months"],
                data["opened_at"],
                data["closed_at"],
                data["updated_at"],
                id_,
            ),
        )
        conn().commit()
        return self.find_by_id(id_)

    def delete(self, id_: str) -> bool:
        cur = conn().execute("DELETE FROM investment_cases WHERE id = ?", (id_,))
        conn().commit()
        return cur.rowcount > 0


class ThesisRevisionsRepository:
    def find_by_id(self, id_: str) -> ThesisRevision | None:
        cur = conn().execute(
            "SELECT * FROM thesis_revisions WHERE id = ?", (id_,)
        )
        row = fetchone_dict(cur)
        return ThesisRevision.model_validate(row) if row else None

    def list_by_case(self, investment_case_id: str) -> list[ThesisRevision]:
        cur = conn().execute(
            """
            SELECT * FROM thesis_revisions
            WHERE investment_case_id = ?
            ORDER BY revision_number DESC
            """,
            (investment_case_id,),
        )
        return [ThesisRevision.model_validate(r) for r in fetchall_dicts(cur)]

    def find_latest(self, investment_case_id: str) -> ThesisRevision | None:
        cur = conn().execute(
            """
            SELECT * FROM thesis_revisions
            WHERE investment_case_id = ?
            ORDER BY revision_number DESC
            LIMIT 1
            """,
            (investment_case_id,),
        )
        row = fetchone_dict(cur)
        return ThesisRevision.model_validate(row) if row else None

    def next_revision_number(self, investment_case_id: str) -> int:
        cur = conn().execute(
            """
            SELECT COALESCE(MAX(revision_number), 0) AS max_rev
            FROM thesis_revisions
            WHERE investment_case_id = ?
            """,
            (investment_case_id,),
        )
        row = fetchone_dict(cur)
        return int(row["max_rev"] if row else 0) + 1

    def create(
        self, input_: CreateThesisRevisionInput, *, revision_number: int
    ) -> ThesisRevision:
        id_ = input_.id or new_id()
        ts = now_ms()
        effective = input_.effective_at if input_.effective_at is not None else ts
        conn().execute(
            """
            INSERT INTO thesis_revisions (
              id, investment_case_id, revision_number, revision_type, thesis,
              bull_case, base_case, bear_case, catalysts, risks,
              invalidation_conditions, target_price_paise, conviction,
              effective_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_,
                input_.investment_case_id,
                revision_number,
                input_.revision_type,
                input_.thesis,
                input_.bull_case,
                input_.base_case,
                input_.bear_case,
                input_.catalysts,
                input_.risks,
                input_.invalidation_conditions,
                input_.target_price_paise,
                input_.conviction,
                effective,
                ts,
            ),
        )
        conn().commit()
        created = self.find_by_id(id_)
        if not created:
            raise RuntimeError(f"Failed to create thesis revision: {id_}")
        return created

    def delete(self, id_: str) -> bool:
        cur = conn().execute(
            "DELETE FROM thesis_revisions WHERE id = ?", (id_,)
        )
        conn().commit()
        return cur.rowcount > 0


investment_cases_repository = InvestmentCasesRepository()
thesis_revisions_repository = ThesisRevisionsRepository()

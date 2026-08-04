"""Portfolios and portfolio accounts repositories."""

from __future__ import annotations

from midas.db.helpers import new_id, now_ms
from midas.db.models import (
    CreatePortfolioAccountInput,
    CreatePortfolioInput,
    Portfolio,
    PortfolioAccount,
    UpdatePortfolioAccountInput,
    UpdatePortfolioInput,
)
from midas.db.repositories.base import conn, fetchall_dicts, fetchone_dict


class PortfoliosRepository:
    def find_by_id(self, id_: str) -> Portfolio | None:
        cur = conn().execute("SELECT * FROM portfolios WHERE id = ?", (id_,))
        row = fetchone_dict(cur)
        return Portfolio.model_validate(row) if row else None

    def list(self, *, include_archived: bool = False) -> list[Portfolio]:
        if include_archived:
            cur = conn().execute("SELECT * FROM portfolios ORDER BY name")
        else:
            cur = conn().execute(
                """
                SELECT * FROM portfolios
                WHERE archived_at IS NULL
                ORDER BY name
                """
            )
        return [Portfolio.model_validate(r) for r in fetchall_dicts(cur)]

    def create(self, input_: CreatePortfolioInput) -> Portfolio:
        id_ = input_.id or new_id()
        ts = now_ms()
        conn().execute(
            """
            INSERT INTO portfolios (
              id, name, description, strategy, base_currency,
              target_capital_paise, created_at, updated_at, archived_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                id_,
                input_.name,
                input_.description,
                input_.strategy,
                input_.base_currency or "INR",
                input_.target_capital_paise,
                ts,
                ts,
            ),
        )
        conn().commit()
        created = self.find_by_id(id_)
        if not created:
            raise RuntimeError(f"Failed to create portfolio: {id_}")
        return created

    def update(self, id_: str, input_: UpdatePortfolioInput) -> Portfolio | None:
        existing = self.find_by_id(id_)
        if not existing:
            return None
        data = existing.model_dump()
        data.update(input_.model_dump(exclude_unset=True))
        data["updated_at"] = now_ms()
        conn().execute(
            """
            UPDATE portfolios SET
              name = ?, description = ?, strategy = ?, base_currency = ?,
              target_capital_paise = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data["name"],
                data["description"],
                data["strategy"],
                data["base_currency"],
                data["target_capital_paise"],
                data["updated_at"],
                id_,
            ),
        )
        conn().commit()
        return self.find_by_id(id_)

    def archive(self, id_: str, archived_at: int | None = None) -> Portfolio | None:
        if not self.find_by_id(id_):
            return None
        ts = now_ms()
        conn().execute(
            """
            UPDATE portfolios SET archived_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (archived_at if archived_at is not None else ts, ts, id_),
        )
        conn().commit()
        return self.find_by_id(id_)

    def unarchive(self, id_: str) -> Portfolio | None:
        if not self.find_by_id(id_):
            return None
        conn().execute(
            """
            UPDATE portfolios SET archived_at = NULL, updated_at = ?
            WHERE id = ?
            """,
            (now_ms(), id_),
        )
        conn().commit()
        return self.find_by_id(id_)

    def delete(self, id_: str) -> bool:
        cur = conn().execute("DELETE FROM portfolios WHERE id = ?", (id_,))
        conn().commit()
        return cur.rowcount > 0


class PortfolioAccountsRepository:
    def find_by_id(self, id_: str) -> PortfolioAccount | None:
        cur = conn().execute(
            "SELECT * FROM portfolio_accounts WHERE id = ?", (id_,)
        )
        row = fetchone_dict(cur)
        return PortfolioAccount.model_validate(row) if row else None

    def list_by_portfolio(self, portfolio_id: str) -> list[PortfolioAccount]:
        cur = conn().execute(
            """
            SELECT * FROM portfolio_accounts
            WHERE portfolio_id = ?
            ORDER BY name
            """,
            (portfolio_id,),
        )
        return [PortfolioAccount.model_validate(r) for r in fetchall_dicts(cur)]

    def create(self, input_: CreatePortfolioAccountInput) -> PortfolioAccount:
        id_ = input_.id or new_id()
        ts = now_ms()
        conn().execute(
            """
            INSERT INTO portfolio_accounts (
              id, portfolio_id, name, institution, account_reference,
              currency, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_,
                input_.portfolio_id,
                input_.name,
                input_.institution,
                input_.account_reference,
                input_.currency or "INR",
                ts,
                ts,
            ),
        )
        conn().commit()
        created = self.find_by_id(id_)
        if not created:
            raise RuntimeError(f"Failed to create portfolio account: {id_}")
        return created

    def update(
        self, id_: str, input_: UpdatePortfolioAccountInput
    ) -> PortfolioAccount | None:
        existing = self.find_by_id(id_)
        if not existing:
            return None
        data = existing.model_dump()
        data.update(input_.model_dump(exclude_unset=True))
        data["updated_at"] = now_ms()
        conn().execute(
            """
            UPDATE portfolio_accounts SET
              name = ?, institution = ?, account_reference = ?,
              currency = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data["name"],
                data["institution"],
                data["account_reference"],
                data["currency"],
                data["updated_at"],
                id_,
            ),
        )
        conn().commit()
        return self.find_by_id(id_)

    def delete(self, id_: str) -> bool:
        cur = conn().execute(
            "DELETE FROM portfolio_accounts WHERE id = ?", (id_,)
        )
        conn().commit()
        return cur.rowcount > 0


portfolios_repository = PortfoliosRepository()
portfolio_accounts_repository = PortfolioAccountsRepository()

"""Securities repository."""

from __future__ import annotations

from midas.db.helpers import from_sqlite_bool, new_id, now_ms, to_sqlite_bool
from midas.db.models import CreateSecurityInput, Security, UpdateSecurityInput
from midas.db.repositories.base import conn, fetchall_dicts, fetchone_dict


def _map_security(row: dict) -> Security:
    data = dict(row)
    data["is_active"] = from_sqlite_bool(data["is_active"])
    return Security.model_validate(data)


class SecuritiesRepository:
    def find_by_id(self, id_: str) -> Security | None:
        cur = conn().execute("SELECT * FROM securities WHERE id = ?", (id_,))
        row = fetchone_dict(cur)
        return _map_security(row) if row else None

    def find_by_exchange_ticker(self, exchange: str, ticker: str) -> Security | None:
        cur = conn().execute(
            """
            SELECT * FROM securities
            WHERE exchange = ? AND ticker = ?
            """,
            (exchange, ticker),
        )
        row = fetchone_dict(cur)
        return _map_security(row) if row else None

    def list_by_company(self, company_id: str) -> list[Security]:
        cur = conn().execute(
            """
            SELECT * FROM securities
            WHERE company_id = ?
            ORDER BY exchange, ticker
            """,
            (company_id,),
        )
        return [_map_security(r) for r in fetchall_dicts(cur)]

    def list(
        self, *, active_only: bool = False, company_id: str | None = None
    ) -> list[Security]:
        clauses: list[str] = []
        params: list[object] = []
        if active_only:
            clauses.append("is_active = 1")
        if company_id:
            clauses.append("company_id = ?")
            params.append(company_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cur = conn().execute(
            f"""
            SELECT * FROM securities
            {where}
            ORDER BY exchange, ticker
            """,
            params,
        )
        return [_map_security(r) for r in fetchall_dicts(cur)]

    def create(self, input_: CreateSecurityInput) -> Security:
        id_ = input_.id or new_id()
        ts = now_ms()
        conn().execute(
            """
            INSERT INTO securities (
              id, company_id, ticker, exchange, name, security_type,
              currency, isin, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_,
                input_.company_id,
                input_.ticker,
                input_.exchange,
                input_.name,
                input_.security_type,
                input_.currency,
                input_.isin,
                to_sqlite_bool(input_.is_active),
                ts,
                ts,
            ),
        )
        conn().commit()
        created = self.find_by_id(id_)
        if not created:
            raise RuntimeError(f"Failed to create security: {id_}")
        return created

    def update(self, id_: str, input_: UpdateSecurityInput) -> Security | None:
        existing = self.find_by_id(id_)
        if not existing:
            return None
        data = existing.model_dump()
        patch = input_.model_dump(exclude_unset=True)
        data.update(patch)
        data["updated_at"] = now_ms()
        conn().execute(
            """
            UPDATE securities SET
              company_id = ?, ticker = ?, exchange = ?, name = ?,
              security_type = ?, currency = ?, isin = ?, is_active = ?,
              updated_at = ?
            WHERE id = ?
            """,
            (
                data["company_id"],
                data["ticker"],
                data["exchange"],
                data["name"],
                data["security_type"],
                data["currency"],
                data["isin"],
                to_sqlite_bool(bool(data["is_active"])),
                data["updated_at"],
                id_,
            ),
        )
        conn().commit()
        return self.find_by_id(id_)

    def delete(self, id_: str) -> bool:
        cur = conn().execute("DELETE FROM securities WHERE id = ?", (id_,))
        conn().commit()
        return cur.rowcount > 0


securities_repository = SecuritiesRepository()

"""Companies repository."""

from __future__ import annotations

from midas.db.helpers import new_id, now_ms
from midas.db.models import (
    Company,
    CompanyStatsBucket,
    CreateCompanyInput,
    MarketCapBucket,
    UpdateCompanyInput,
)
from midas.db.repositories.base import conn, fetchall_dicts, fetchone_dict


class CompaniesRepository:
    def find_by_id(self, id_: str) -> Company | None:
        cur = conn().execute("SELECT * FROM companies WHERE id = ?", (id_,))
        row = fetchone_dict(cur)
        return Company.model_validate(row) if row else None

    def list(
        self,
        *,
        sector: str | None = None,
        industry: str | None = None,
        market_cap_bucket: MarketCapBucket | None = None,
        limit: int = 5000,
    ) -> list[Company]:
        clauses: list[str] = []
        params: list[object] = []
        if sector:
            clauses.append("sector = ?")
            params.append(sector)
        if industry:
            clauses.append("industry = ?")
            params.append(industry)
        if market_cap_bucket:
            clauses.append("market_cap_bucket = ?")
            params.append(market_cap_bucket)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        cur = conn().execute(
            f"""
            SELECT * FROM companies
            {where}
            ORDER BY name
            LIMIT ?
            """,
            params,
        )
        return [Company.model_validate(r) for r in fetchall_dicts(cur)]

    def create(self, input_: CreateCompanyInput) -> Company:
        id_ = input_.id or new_id()
        ts = now_ms()
        conn().execute(
            """
            INSERT INTO companies (
              id, name, legal_name, sector, industry, market_cap_bucket,
              country_code, website, classification_source,
              classification_as_of, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_,
                input_.name,
                input_.legal_name,
                input_.sector,
                input_.industry,
                input_.market_cap_bucket,
                input_.country_code or "IN",
                input_.website,
                input_.classification_source,
                input_.classification_as_of,
                input_.notes,
                ts,
                ts,
            ),
        )
        conn().commit()
        created = self.find_by_id(id_)
        if not created:
            raise RuntimeError(f"Failed to create company: {id_}")
        return created

    def update(self, id_: str, input_: UpdateCompanyInput) -> Company | None:
        existing = self.find_by_id(id_)
        if not existing:
            return None
        data = existing.model_dump()
        patch = input_.model_dump(exclude_unset=True)
        data.update(patch)
        data["updated_at"] = now_ms()
        conn().execute(
            """
            UPDATE companies SET
              name = ?, legal_name = ?, sector = ?, industry = ?,
              market_cap_bucket = ?, country_code = ?, website = ?,
              classification_source = ?, classification_as_of = ?,
              notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data["name"],
                data["legal_name"],
                data["sector"],
                data["industry"],
                data["market_cap_bucket"],
                data["country_code"],
                data["website"],
                data["classification_source"],
                data["classification_as_of"],
                data["notes"],
                data["updated_at"],
                id_,
            ),
        )
        conn().commit()
        return self.find_by_id(id_)

    def delete(self, id_: str) -> bool:
        cur = conn().execute("DELETE FROM companies WHERE id = ?", (id_,))
        conn().commit()
        return cur.rowcount > 0

    def count_by_sector(self) -> list[CompanyStatsBucket]:
        cur = conn().execute(
            """
            SELECT COALESCE(sector, 'UNKNOWN') AS key, COUNT(*) AS company_count
            FROM companies
            GROUP BY COALESCE(sector, 'UNKNOWN')
            ORDER BY company_count DESC, key
            """
        )
        return [CompanyStatsBucket.model_validate(r) for r in fetchall_dicts(cur)]

    def count_by_industry(self) -> list[CompanyStatsBucket]:
        cur = conn().execute(
            """
            SELECT COALESCE(industry, 'UNKNOWN') AS key, COUNT(*) AS company_count
            FROM companies
            GROUP BY COALESCE(industry, 'UNKNOWN')
            ORDER BY company_count DESC, key
            """
        )
        return [CompanyStatsBucket.model_validate(r) for r in fetchall_dicts(cur)]

    def count_by_market_cap_bucket(self) -> list[CompanyStatsBucket]:
        cur = conn().execute(
            """
            SELECT COALESCE(market_cap_bucket, 'UNKNOWN') AS key,
                   COUNT(*) AS company_count
            FROM companies
            GROUP BY COALESCE(market_cap_bucket, 'UNKNOWN')
            ORDER BY company_count DESC, key
            """
        )
        return [CompanyStatsBucket.model_validate(r) for r in fetchall_dicts(cur)]


companies_repository = CompaniesRepository()

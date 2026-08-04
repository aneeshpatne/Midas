"""Research runs, evidence, securities, and portfolio-link repositories."""

from __future__ import annotations

from datetime import UTC, datetime

from midas.db.helpers import new_id, now_ms
from midas.db.models import (
    AddResearchRunSecurityInput,
    AppendResearchEvidenceInput,
    CreateResearchPortfolioLinkInput,
    CreateResearchRunInput,
    ResearchEvidence,
    ResearchPortfolioLink,
    ResearchRun,
    ResearchRunSecurity,
    ResearchRunStatus,
    ResearchWorkflow,
    UpdateResearchRunInput,
)
from midas.db.repositories.base import conn, fetchall_dicts, fetchone_dict


def format_run_key(timestamp_ms: int | None = None) -> str:
    ts = timestamp_ms if timestamp_ms is not None else now_ms()
    d = datetime.fromtimestamp(ts / 1000, tz=UTC)
    return d.strftime("%Y%m%dT%H%M%SZ")


class ResearchRunsRepository:
    def find_by_id(self, id_: str) -> ResearchRun | None:
        cur = conn().execute("SELECT * FROM research_runs WHERE id = ?", (id_,))
        row = fetchone_dict(cur)
        return ResearchRun.model_validate(row) if row else None

    def find_by_slug_run_key(self, slug: str, run_key: str) -> ResearchRun | None:
        cur = conn().execute(
            """
            SELECT * FROM research_runs
            WHERE slug = ? AND run_key = ?
            """,
            (slug, run_key),
        )
        row = fetchone_dict(cur)
        return ResearchRun.model_validate(row) if row else None

    def list(
        self,
        *,
        slug: str | None = None,
        status: ResearchRunStatus | None = None,
        workflow: ResearchWorkflow | None = None,
        limit: int = 100,
    ) -> list[ResearchRun]:
        clauses: list[str] = []
        params: list[object] = []
        if slug:
            clauses.append("slug = ?")
            params.append(slug)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if workflow:
            clauses.append("workflow = ?")
            params.append(workflow)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        cur = conn().execute(
            f"""
            SELECT * FROM research_runs
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        )
        return [ResearchRun.model_validate(r) for r in fetchall_dicts(cur)]

    def create(self, input_: CreateResearchRunInput) -> ResearchRun:
        id_ = input_.id or new_id()
        ts = now_ms()
        run_key = input_.run_key or format_run_key(ts)
        cutoff = input_.cutoff_at if input_.cutoff_at is not None else ts
        conn().execute(
            """
            INSERT INTO research_runs (
              id, slug, run_key, workflow, status, title, universe_or_company,
              horizon_text, horizon_months, cutoff_at, mandate_md, report_md,
              primary_runtime, execution_mode, created_at, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                id_,
                input_.slug,
                run_key,
                input_.workflow,
                input_.status,
                input_.title,
                input_.universe_or_company,
                input_.horizon_text,
                input_.horizon_months,
                cutoff,
                input_.mandate_md,
                input_.report_md,
                input_.primary_runtime,
                input_.execution_mode,
                ts,
                ts,
            ),
        )
        conn().commit()
        created = self.find_by_id(id_)
        if not created:
            raise RuntimeError(f"Failed to create research run: {id_}")
        return created

    def update(
        self, id_: str, input_: UpdateResearchRunInput
    ) -> ResearchRun | None:
        existing = self.find_by_id(id_)
        if not existing:
            return None
        data = existing.model_dump()
        patch = input_.model_dump(exclude_unset=True)
        data.update(patch)
        data["updated_at"] = now_ms()

        if (
            patch.get("status") == "COMPLETED"
            and existing.completed_at is None
        ):
            data["completed_at"] = now_ms()
        elif (
            "status" in patch
            and patch["status"] != "COMPLETED"
            and existing.status == "COMPLETED"
        ):
            data["completed_at"] = None

        conn().execute(
            """
            UPDATE research_runs SET
              title = ?, universe_or_company = ?, horizon_text = ?,
              horizon_months = ?, cutoff_at = ?, mandate_md = ?, report_md = ?,
              primary_runtime = ?, execution_mode = ?, status = ?,
              updated_at = ?, completed_at = ?
            WHERE id = ?
            """,
            (
                data["title"],
                data["universe_or_company"],
                data["horizon_text"],
                data["horizon_months"],
                data["cutoff_at"],
                data["mandate_md"],
                data["report_md"],
                data["primary_runtime"],
                data["execution_mode"],
                data["status"],
                data["updated_at"],
                data["completed_at"],
                id_,
            ),
        )
        conn().commit()
        return self.find_by_id(id_)

    def delete(self, id_: str) -> bool:
        cur = conn().execute("DELETE FROM research_runs WHERE id = ?", (id_,))
        conn().commit()
        return cur.rowcount > 0


class ResearchRunSecuritiesRepository:
    def find_by_id(self, id_: str) -> ResearchRunSecurity | None:
        cur = conn().execute(
            "SELECT * FROM research_run_securities WHERE id = ?", (id_,)
        )
        row = fetchone_dict(cur)
        return ResearchRunSecurity.model_validate(row) if row else None

    def list_by_run(self, research_run_id: str) -> list[ResearchRunSecurity]:
        cur = conn().execute(
            """
            SELECT * FROM research_run_securities
            WHERE research_run_id = ?
            ORDER BY sort_order, symbol
            """,
            (research_run_id,),
        )
        return [ResearchRunSecurity.model_validate(r) for r in fetchall_dicts(cur)]

    def add(self, input_: AddResearchRunSecurityInput) -> ResearchRunSecurity:
        id_ = input_.id or new_id()
        ts = now_ms()
        conn().execute(
            """
            INSERT INTO research_run_securities (
              id, research_run_id, security_id, symbol, exchange, role,
              sort_order, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_,
                input_.research_run_id,
                input_.security_id,
                input_.symbol,
                input_.exchange,
                input_.role,
                input_.sort_order,
                input_.notes,
                ts,
            ),
        )
        conn().commit()
        created = self.find_by_id(id_)
        if not created:
            raise RuntimeError(f"Failed to add research run security: {id_}")
        return created

    def delete(self, id_: str) -> bool:
        cur = conn().execute(
            "DELETE FROM research_run_securities WHERE id = ?", (id_,)
        )
        conn().commit()
        return cur.rowcount > 0


class ResearchEvidenceRepository:
    def find_by_id(self, id_: str) -> ResearchEvidence | None:
        cur = conn().execute(
            "SELECT * FROM research_evidence WHERE id = ?", (id_,)
        )
        row = fetchone_dict(cur)
        return ResearchEvidence.model_validate(row) if row else None

    def list_by_run(
        self,
        research_run_id: str,
        *,
        record_type: str | None = None,
        symbol: str | None = None,
        from_seq: int | None = None,
        limit: int = 10_000,
    ) -> list[ResearchEvidence]:
        clauses = ["research_run_id = ?"]
        params: list[object] = [research_run_id]
        if record_type:
            clauses.append("record_type = ?")
            params.append(record_type)
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if from_seq is not None:
            clauses.append("seq >= ?")
            params.append(from_seq)
        params.append(limit)
        cur = conn().execute(
            f"""
            SELECT * FROM research_evidence
            WHERE {" AND ".join(clauses)}
            ORDER BY seq ASC
            LIMIT ?
            """,
            params,
        )
        return [ResearchEvidence.model_validate(r) for r in fetchall_dicts(cur)]

    def next_seq(self, research_run_id: str) -> int:
        cur = conn().execute(
            """
            SELECT MAX(seq) AS max_seq FROM research_evidence
            WHERE research_run_id = ?
            """,
            (research_run_id,),
        )
        row = fetchone_dict(cur)
        max_seq = row["max_seq"] if row else None
        return (int(max_seq) if max_seq is not None else 0) + 1

    def append(
        self,
        input_: AppendResearchEvidenceInput,
        *,
        seq: int,
        payload_json: str,
    ) -> ResearchEvidence:
        id_ = input_.id or new_id()
        ts = now_ms()
        conn().execute(
            """
            INSERT INTO research_evidence (
              id, research_run_id, record_type, record_id, seq, payload_json,
              as_of, security_id, symbol, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_,
                input_.research_run_id,
                input_.record_type,
                input_.record_id,
                seq,
                payload_json,
                input_.as_of,
                input_.security_id,
                input_.symbol,
                ts,
            ),
        )
        conn().commit()
        created = self.find_by_id(id_)
        if not created:
            raise RuntimeError(f"Failed to append research evidence: {id_}")
        return created


class ResearchPortfolioLinksRepository:
    def find_by_id(self, id_: str) -> ResearchPortfolioLink | None:
        cur = conn().execute(
            "SELECT * FROM research_portfolio_links WHERE id = ?", (id_,)
        )
        row = fetchone_dict(cur)
        return ResearchPortfolioLink.model_validate(row) if row else None

    def list_by_run(self, research_run_id: str) -> list[ResearchPortfolioLink]:
        cur = conn().execute(
            """
            SELECT * FROM research_portfolio_links
            WHERE research_run_id = ?
            ORDER BY created_at DESC
            """,
            (research_run_id,),
        )
        return [
            ResearchPortfolioLink.model_validate(r) for r in fetchall_dicts(cur)
        ]

    def list_by_portfolio(self, portfolio_id: str) -> list[ResearchPortfolioLink]:
        cur = conn().execute(
            """
            SELECT * FROM research_portfolio_links
            WHERE portfolio_id = ?
            ORDER BY created_at DESC
            """,
            (portfolio_id,),
        )
        return [
            ResearchPortfolioLink.model_validate(r) for r in fetchall_dicts(cur)
        ]

    def list_by_investment_case(
        self, investment_case_id: str
    ) -> list[ResearchPortfolioLink]:
        cur = conn().execute(
            """
            SELECT * FROM research_portfolio_links
            WHERE investment_case_id = ?
            ORDER BY created_at DESC
            """,
            (investment_case_id,),
        )
        return [
            ResearchPortfolioLink.model_validate(r) for r in fetchall_dicts(cur)
        ]

    def create(
        self, input_: CreateResearchPortfolioLinkInput
    ) -> ResearchPortfolioLink:
        id_ = input_.id or new_id()
        ts = now_ms()
        conn().execute(
            """
            INSERT INTO research_portfolio_links (
              id, research_run_id, portfolio_id, investment_case_id,
              link_role, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_,
                input_.research_run_id,
                input_.portfolio_id,
                input_.investment_case_id,
                input_.link_role,
                input_.notes,
                ts,
            ),
        )
        conn().commit()
        created = self.find_by_id(id_)
        if not created:
            raise RuntimeError(f"Failed to create research portfolio link: {id_}")
        return created

    def delete(self, id_: str) -> bool:
        cur = conn().execute(
            "DELETE FROM research_portfolio_links WHERE id = ?", (id_,)
        )
        conn().commit()
        return cur.rowcount > 0


research_runs_repository = ResearchRunsRepository()
research_run_securities_repository = ResearchRunSecuritiesRepository()
research_evidence_repository = ResearchEvidenceRepository()
research_portfolio_links_repository = ResearchPortfolioLinksRepository()

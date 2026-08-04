"""Versioned SQLite migrations for Midas DB (versions 1–3)."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .connection import close, configure, connect, get_connection, get_db_path
from .helpers import now_ms

logger = logging.getLogger(__name__)

# Final-form bootstrap for empty DBs / replication (CREATE TABLE IF NOT EXISTS).
BOOTSTRAP_SQL_PATH = Path(__file__).with_name("schema.bootstrap.sql")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        name="create_portfolio_schema",
        sql="""
      CREATE TABLE securities (
        id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        exchange TEXT NOT NULL,
        name TEXT NOT NULL,
        security_type TEXT NOT NULL DEFAULT 'EQUITY'
          CHECK (
            security_type IN (
              'EQUITY','ETF','MUTUAL_FUND','BOND','REIT','CRYPTO','OTHER'
            )
          ),
        currency TEXT NOT NULL,
        isin TEXT,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        UNIQUE (exchange, ticker)
      ) STRICT;

      CREATE TABLE portfolios (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        strategy TEXT,
        base_currency TEXT NOT NULL DEFAULT 'INR',
        target_capital_paise INTEGER
          CHECK (target_capital_paise IS NULL OR target_capital_paise >= 0),
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        archived_at INTEGER
      ) STRICT;

      CREATE TABLE investment_cases (
        id TEXT PRIMARY KEY,
        portfolio_id TEXT NOT NULL,
        security_id TEXT NOT NULL,
        name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'WATCHLIST'
          CHECK (
            status IN (
              'WATCHLIST','ACTIVE','REDUCING','EXITED','INVALIDATED','ARCHIVED'
            )
          ),
        conviction INTEGER
          CHECK (conviction IS NULL OR conviction BETWEEN 1 AND 5),
        time_horizon_months INTEGER
          CHECK (time_horizon_months IS NULL OR time_horizon_months > 0),
        opened_at INTEGER,
        closed_at INTEGER,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE,
        FOREIGN KEY (security_id) REFERENCES securities(id) ON DELETE RESTRICT,
        UNIQUE (portfolio_id, security_id, name)
      ) STRICT;

      CREATE TABLE thesis_revisions (
        id TEXT PRIMARY KEY,
        investment_case_id TEXT NOT NULL,
        revision_number INTEGER NOT NULL,
        revision_type TEXT NOT NULL DEFAULT 'UPDATE'
          CHECK (
            revision_type IN (
              'INITIAL','UPDATE','EARNINGS_UPDATE','RISK_UPDATE',
              'INVALIDATION','EXIT_NOTE'
            )
          ),
        thesis TEXT NOT NULL,
        bull_case TEXT,
        base_case TEXT,
        bear_case TEXT,
        catalysts TEXT,
        risks TEXT,
        invalidation_conditions TEXT,
        target_price_paise INTEGER
          CHECK (target_price_paise IS NULL OR target_price_paise >= 0),
        conviction INTEGER
          CHECK (conviction IS NULL OR conviction BETWEEN 1 AND 5),
        effective_at INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY (investment_case_id)
          REFERENCES investment_cases(id) ON DELETE CASCADE,
        CHECK (revision_number > 0),
        UNIQUE (investment_case_id, revision_number)
      ) STRICT;

      CREATE TABLE portfolio_accounts (
        id TEXT PRIMARY KEY,
        portfolio_id TEXT NOT NULL,
        name TEXT NOT NULL,
        institution TEXT,
        account_reference TEXT,
        currency TEXT NOT NULL DEFAULT 'INR',
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE,
        UNIQUE (portfolio_id, name)
      ) STRICT;

      CREATE TABLE transactions (
        id TEXT PRIMARY KEY,
        portfolio_id TEXT NOT NULL,
        account_id TEXT,
        security_id TEXT,
        investment_case_id TEXT,
        type TEXT NOT NULL
          CHECK (
            type IN (
              'BUY','SELL','DIVIDEND','INTEREST','FEE','TAX',
              'DEPOSIT','WITHDRAWAL','SPLIT','BONUS','TRANSFER_IN','TRANSFER_OUT'
            )
          ),
        quantity_micros INTEGER
          CHECK (quantity_micros IS NULL OR quantity_micros >= 0),
        price_paise INTEGER
          CHECK (price_paise IS NULL OR price_paise >= 0),
        gross_amount_paise INTEGER
          CHECK (gross_amount_paise IS NULL OR gross_amount_paise >= 0),
        fees_paise INTEGER NOT NULL DEFAULT 0 CHECK (fees_paise >= 0),
        taxes_paise INTEGER NOT NULL DEFAULT 0 CHECK (taxes_paise >= 0),
        net_amount_paise INTEGER,
        cash_effect_paise INTEGER NOT NULL,
        currency TEXT NOT NULL DEFAULT 'INR',
        exchange_rate_micros INTEGER NOT NULL DEFAULT 1000000
          CHECK (exchange_rate_micros > 0),
        executed_at INTEGER NOT NULL,
        settlement_date TEXT,
        external_reference TEXT,
        notes TEXT,
        created_at INTEGER NOT NULL,
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE,
        FOREIGN KEY (account_id)
          REFERENCES portfolio_accounts(id) ON DELETE SET NULL,
        FOREIGN KEY (security_id) REFERENCES securities(id) ON DELETE RESTRICT,
        FOREIGN KEY (investment_case_id)
          REFERENCES investment_cases(id) ON DELETE SET NULL,
        CHECK (
          type NOT IN ('BUY','SELL','BONUS','TRANSFER_IN','TRANSFER_OUT')
          OR (
            security_id IS NOT NULL
            AND quantity_micros IS NOT NULL
            AND quantity_micros > 0
          )
        ),
        CHECK (
          type NOT IN ('BUY','SELL')
          OR (price_paise IS NOT NULL AND price_paise >= 0)
        ),
        CHECK (
          type NOT IN (
            'DEPOSIT','WITHDRAWAL','DIVIDEND','INTEREST','FEE','TAX'
          )
          OR (
            gross_amount_paise IS NOT NULL AND gross_amount_paise >= 0
          )
        )
      ) STRICT;

      CREATE TABLE market_prices (
        security_id TEXT NOT NULL,
        price_date TEXT NOT NULL,
        price_paise INTEGER NOT NULL CHECK (price_paise >= 0),
        currency TEXT NOT NULL DEFAULT 'INR',
        source TEXT,
        captured_at INTEGER NOT NULL,
        PRIMARY KEY (security_id, price_date),
        FOREIGN KEY (security_id) REFERENCES securities(id) ON DELETE CASCADE
      ) STRICT;

      CREATE INDEX securities_ticker_idx ON securities(ticker);
      CREATE INDEX investment_cases_portfolio_idx ON investment_cases(portfolio_id);
      CREATE INDEX investment_cases_security_idx ON investment_cases(security_id);
      CREATE INDEX investment_cases_status_idx ON investment_cases(status);
      CREATE INDEX thesis_revisions_case_idx
        ON thesis_revisions(investment_case_id, revision_number DESC);
      CREATE INDEX transactions_portfolio_date_idx
        ON transactions(portfolio_id, executed_at DESC);
      CREATE INDEX transactions_security_date_idx
        ON transactions(security_id, executed_at DESC);
      CREATE INDEX transactions_investment_case_idx
        ON transactions(investment_case_id);
      CREATE INDEX transactions_account_idx ON transactions(account_id);
      CREATE INDEX market_prices_date_idx
        ON market_prices(security_id, price_date DESC);
        """,
    ),
    Migration(
        version=2,
        name="create_research_schema",
        sql="""
      CREATE TABLE research_runs (
        id TEXT PRIMARY KEY,
        slug TEXT NOT NULL,
        run_key TEXT NOT NULL,
        workflow TEXT NOT NULL
          CHECK (
            workflow IN ('single_stock','named_comparison','broad_universe')
          ),
        status TEXT NOT NULL DEFAULT 'IN_PROGRESS'
          CHECK (
            status IN (
              'DRAFT','IN_PROGRESS','COMPLETED','BLOCKED','ABANDONED'
            )
          ),
        title TEXT,
        universe_or_company TEXT NOT NULL,
        horizon_text TEXT NOT NULL,
        horizon_months INTEGER
          CHECK (horizon_months IS NULL OR horizon_months > 0),
        cutoff_at INTEGER NOT NULL,
        mandate_md TEXT,
        report_md TEXT,
        primary_runtime TEXT,
        execution_mode TEXT,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        completed_at INTEGER,
        UNIQUE (slug, run_key)
      ) STRICT;

      CREATE TABLE research_run_securities (
        id TEXT PRIMARY KEY,
        research_run_id TEXT NOT NULL,
        security_id TEXT,
        symbol TEXT NOT NULL,
        exchange TEXT,
        role TEXT NOT NULL DEFAULT 'SUBJECT'
          CHECK (
            role IN (
              'SUBJECT','PEER','BENCHMARK','NEAR_MISS','EXCLUDED'
            )
          ),
        sort_order INTEGER NOT NULL DEFAULT 0,
        notes TEXT,
        created_at INTEGER NOT NULL,
        FOREIGN KEY (research_run_id)
          REFERENCES research_runs(id) ON DELETE CASCADE,
        FOREIGN KEY (security_id)
          REFERENCES securities(id) ON DELETE SET NULL,
        UNIQUE (research_run_id, symbol, role)
      ) STRICT;

      CREATE TABLE research_evidence (
        id TEXT PRIMARY KEY,
        research_run_id TEXT NOT NULL,
        record_type TEXT NOT NULL,
        record_id TEXT,
        seq INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        as_of INTEGER,
        security_id TEXT,
        symbol TEXT,
        created_at INTEGER NOT NULL,
        FOREIGN KEY (research_run_id)
          REFERENCES research_runs(id) ON DELETE CASCADE,
        FOREIGN KEY (security_id)
          REFERENCES securities(id) ON DELETE SET NULL,
        CHECK (seq > 0),
        UNIQUE (research_run_id, seq)
      ) STRICT;

      CREATE TABLE research_portfolio_links (
        id TEXT PRIMARY KEY,
        research_run_id TEXT NOT NULL,
        portfolio_id TEXT NOT NULL,
        investment_case_id TEXT,
        link_role TEXT NOT NULL DEFAULT 'ADMISSION'
          CHECK (
            link_role IN (
              'ADMISSION','CONTEXT','REBALANCE_INPUT','THESIS_VALIDATION'
            )
          ),
        notes TEXT,
        created_at INTEGER NOT NULL,
        FOREIGN KEY (research_run_id)
          REFERENCES research_runs(id) ON DELETE CASCADE,
        FOREIGN KEY (portfolio_id)
          REFERENCES portfolios(id) ON DELETE CASCADE,
        FOREIGN KEY (investment_case_id)
          REFERENCES investment_cases(id) ON DELETE SET NULL,
        UNIQUE (
          research_run_id, portfolio_id, link_role, investment_case_id
        )
      ) STRICT;

      CREATE INDEX research_runs_slug_idx
        ON research_runs(slug, created_at DESC);
      CREATE INDEX research_runs_status_idx
        ON research_runs(status, updated_at DESC);
      CREATE INDEX research_runs_cutoff_idx
        ON research_runs(cutoff_at DESC);
      CREATE INDEX research_run_securities_run_idx
        ON research_run_securities(research_run_id, sort_order);
      CREATE INDEX research_run_securities_security_idx
        ON research_run_securities(security_id);
      CREATE INDEX research_evidence_run_seq_idx
        ON research_evidence(research_run_id, seq);
      CREATE INDEX research_evidence_run_type_idx
        ON research_evidence(research_run_id, record_type);
      CREATE INDEX research_evidence_symbol_idx
        ON research_evidence(research_run_id, symbol);
      CREATE INDEX research_portfolio_links_run_idx
        ON research_portfolio_links(research_run_id);
      CREATE INDEX research_portfolio_links_portfolio_idx
        ON research_portfolio_links(portfolio_id);
      CREATE INDEX research_portfolio_links_case_idx
        ON research_portfolio_links(investment_case_id);
        """,
    ),
    Migration(
        version=3,
        name="create_companies_and_link_securities",
        sql="""
      CREATE TABLE companies (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        legal_name TEXT,
        sector TEXT,
        industry TEXT,
        market_cap_bucket TEXT
          CHECK (
            market_cap_bucket IS NULL
            OR market_cap_bucket IN (
              'LARGE','MID','SMALL','MICRO','OTHER'
            )
          ),
        country_code TEXT NOT NULL DEFAULT 'IN',
        website TEXT,
        classification_source TEXT,
        classification_as_of TEXT,
        notes TEXT,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
      ) STRICT;

      ALTER TABLE securities
        ADD COLUMN company_id TEXT
          REFERENCES companies(id)
          ON DELETE SET NULL;

      CREATE INDEX companies_name_idx ON companies(name);
      CREATE INDEX companies_sector_idx ON companies(sector);
      CREATE INDEX companies_industry_idx ON companies(industry);
      CREATE INDEX companies_market_cap_bucket_idx
        ON companies(market_cap_bucket);
      CREATE INDEX securities_company_idx ON securities(company_id);
        """,
    ),
]


def _prepare_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          applied_at INTEGER NOT NULL
        ) STRICT
        """
    )


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    return {int(row["version"]) for row in rows}


def _apply_migration(conn: sqlite3.Connection, migration: Migration) -> None:
    conn.executescript(migration.sql)
    conn.execute(
        """
        INSERT INTO schema_migrations (version, name, applied_at)
        VALUES (?, ?, ?)
        """,
        (migration.version, migration.name, now_ms()),
    )


def run_migrations(path: str | Path | None = None) -> None:
    """Apply pending migrations 1–3 to the configured (or given) DB path."""
    if path is not None:
        configure(path)
        close()

    conn = get_connection()
    _prepare_migration_table(conn)
    applied = _applied_versions(conn)

    for migration in MIGRATIONS:
        if migration.version in applied:
            logger.info(
                "Migration %s already applied: %s",
                migration.version,
                migration.name,
            )
            continue
        logger.info(
            "Applying migration %s: %s", migration.version, migration.name
        )
        try:
            _apply_migration(conn, migration)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        logger.info(
            "Applied migration %s: %s", migration.version, migration.name
        )

    problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        raise RuntimeError(f"Database foreign-key check failed: {problems}")

    logger.info("Database migrations completed (db=%s).", get_db_path())


def bootstrap_from_sql(path: str | Path | None = None) -> None:
    """Apply full schema.bootstrap.sql (fresh DB / replication)."""
    if path is not None:
        configure(path)
        close()
    sql = BOOTSTRAP_SQL_PATH.read_text(encoding="utf-8")
    conn = connect()  # fresh connection so PRAGMAs in file apply cleanly
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()
    close()  # drop thread-local so next get_connection sees new schema
    logger.info("Bootstrap applied from %s", BOOTSTRAP_SQL_PATH)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    run_migrations()
    print(f"Midas DB migrations completed: {get_db_path()}")


if __name__ == "__main__":
    main()

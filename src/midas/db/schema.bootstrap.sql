-- Midas DB — full bootstrap for replication
-- Engine: SQLite 3 (STRICT tables)
-- Source of truth: src/midas/db/migrate.py (versions 1–4)
--
-- Usage:
--   sqlite3 midas.db < src/midas/db/schema.bootstrap.sql
--
-- Or with Python app:
--   python -m midas.db.migrate
--
-- Required runtime PRAGMAs (also set by src/midas/db/connection.py):
--   PRAGMA foreign_keys = ON;
--   PRAGMA journal_mode = WAL;
--   PRAGMA busy_timeout = 5000;

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

BEGIN;

-- ---------------------------------------------------------------------------
-- Migration bookkeeping
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at INTEGER NOT NULL
) STRICT;

-- ---------------------------------------------------------------------------
-- Companies (issuer metadata; optional parent of listings)
-- ---------------------------------------------------------------------------
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
        'LARGE',
        'MID',
        'SMALL',
        'MICRO',
        'OTHER'
      )
    ),

  country_code TEXT NOT NULL DEFAULT 'IN',
  website TEXT,

  -- Point-in-time classification provenance (e.g. AMFI vintage).
  classification_source TEXT,
  classification_as_of TEXT,

  notes TEXT,

  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
) STRICT;

CREATE INDEX companies_name_idx ON companies(name);
CREATE INDEX companies_sector_idx ON companies(sector);
CREATE INDEX companies_industry_idx ON companies(industry);
CREATE INDEX companies_market_cap_bucket_idx ON companies(market_cap_bucket);

-- ---------------------------------------------------------------------------
-- Securities master (tradable listings)
-- ---------------------------------------------------------------------------
CREATE TABLE securities (
  id TEXT PRIMARY KEY,

  company_id TEXT
    REFERENCES companies(id)
    ON DELETE SET NULL,

  ticker TEXT NOT NULL,
  exchange TEXT NOT NULL,
  name TEXT NOT NULL,

  security_type TEXT NOT NULL DEFAULT 'EQUITY'
    CHECK (
      security_type IN (
        'EQUITY',
        'ETF',
        'MUTUAL_FUND',
        'BOND',
        'REIT',
        'CRYPTO',
        'OTHER'
      )
    ),

  currency TEXT NOT NULL,
  isin TEXT,

  is_active INTEGER NOT NULL DEFAULT 1
    CHECK (is_active IN (0, 1)),

  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,

  UNIQUE (exchange, ticker)
) STRICT;

CREATE INDEX securities_ticker_idx ON securities(ticker);
CREATE INDEX securities_company_idx ON securities(company_id);

-- ---------------------------------------------------------------------------
-- Paper portfolios
-- ---------------------------------------------------------------------------
CREATE TABLE portfolios (
  id TEXT PRIMARY KEY,

  name TEXT NOT NULL,
  description TEXT,
  strategy TEXT,

  base_currency TEXT NOT NULL DEFAULT 'INR',

  -- Planned budget only; actual funding is DEPOSIT/WITHDRAWAL cash effects.
  target_capital_paise INTEGER
    CHECK (
      target_capital_paise IS NULL
      OR target_capital_paise >= 0
    ),

  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  archived_at INTEGER
) STRICT;

-- ---------------------------------------------------------------------------
-- Broker / custody sleeves inside a portfolio (optional)
-- ---------------------------------------------------------------------------
CREATE TABLE portfolio_accounts (
  id TEXT PRIMARY KEY,

  portfolio_id TEXT NOT NULL,

  name TEXT NOT NULL,
  institution TEXT,
  account_reference TEXT,
  currency TEXT NOT NULL DEFAULT 'INR',

  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,

  FOREIGN KEY (portfolio_id)
    REFERENCES portfolios(id)
    ON DELETE CASCADE,

  UNIQUE (portfolio_id, name)
) STRICT;

-- ---------------------------------------------------------------------------
-- Investment cases (thesis-backed position intent per name in a portfolio)
-- ---------------------------------------------------------------------------
CREATE TABLE investment_cases (
  id TEXT PRIMARY KEY,

  portfolio_id TEXT NOT NULL,
  security_id TEXT NOT NULL,

  name TEXT NOT NULL,

  status TEXT NOT NULL DEFAULT 'WATCHLIST'
    CHECK (
      status IN (
        'WATCHLIST',
        'ACTIVE',
        'REDUCING',
        'EXITED',
        'INVALIDATED',
        'ARCHIVED'
      )
    ),

  conviction INTEGER
    CHECK (
      conviction IS NULL
      OR conviction BETWEEN 1 AND 5
    ),

  time_horizon_months INTEGER
    CHECK (
      time_horizon_months IS NULL
      OR time_horizon_months > 0
    ),

  opened_at INTEGER,
  closed_at INTEGER,

  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,

  FOREIGN KEY (portfolio_id)
    REFERENCES portfolios(id)
    ON DELETE CASCADE,

  FOREIGN KEY (security_id)
    REFERENCES securities(id)
    ON DELETE RESTRICT,

  UNIQUE (portfolio_id, security_id, name)
) STRICT;

CREATE INDEX investment_cases_portfolio_idx ON investment_cases(portfolio_id);
CREATE INDEX investment_cases_security_idx ON investment_cases(security_id);
CREATE INDEX investment_cases_status_idx ON investment_cases(status);

-- ---------------------------------------------------------------------------
-- Thesis revision history (append-style versioned writeups)
-- ---------------------------------------------------------------------------
CREATE TABLE thesis_revisions (
  id TEXT PRIMARY KEY,

  investment_case_id TEXT NOT NULL,
  revision_number INTEGER NOT NULL,

  revision_type TEXT NOT NULL DEFAULT 'UPDATE'
    CHECK (
      revision_type IN (
        'INITIAL',
        'UPDATE',
        'EARNINGS_UPDATE',
        'RISK_UPDATE',
        'INVALIDATION',
        'EXIT_NOTE'
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
    CHECK (
      target_price_paise IS NULL
      OR target_price_paise >= 0
    ),

  conviction INTEGER
    CHECK (
      conviction IS NULL
      OR conviction BETWEEN 1 AND 5
    ),

  effective_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,

  FOREIGN KEY (investment_case_id)
    REFERENCES investment_cases(id)
    ON DELETE CASCADE,

  CHECK (revision_number > 0),

  UNIQUE (investment_case_id, revision_number)
) STRICT;

CREATE INDEX thesis_revisions_case_idx
  ON thesis_revisions(investment_case_id, revision_number DESC);

-- ---------------------------------------------------------------------------
-- Approval-gated paper trade proposals
-- ---------------------------------------------------------------------------
CREATE TABLE trade_proposals (
  id TEXT PRIMARY KEY,
  portfolio_id TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'DRAFT'
    CHECK (status IN ('DRAFT','APPROVED','REJECTED','SUPERSEDED','EXECUTED')),
  trades_json TEXT NOT NULL CHECK (json_valid(trades_json)),
  rationale TEXT,
  warnings_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(warnings_json)),
  price_as_of INTEGER NOT NULL,
  expires_at INTEGER,
  approved_at INTEGER,
  rejected_at INTEGER,
  superseded_at INTEGER,
  executed_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
) STRICT;

CREATE INDEX trade_proposals_portfolio_idx
  ON trade_proposals(portfolio_id, created_at DESC);
CREATE INDEX trade_proposals_status_idx ON trade_proposals(status);

-- ---------------------------------------------------------------------------
-- Transaction ledger (cash + positions; source of truth for holdings)
-- ---------------------------------------------------------------------------
CREATE TABLE transactions (
  id TEXT PRIMARY KEY,

  portfolio_id TEXT NOT NULL,
  account_id TEXT,
  security_id TEXT,
  investment_case_id TEXT,
  proposal_id TEXT,

  type TEXT NOT NULL
    CHECK (
      type IN (
        'BUY',
        'SELL',
        'DIVIDEND',
        'INTEREST',
        'FEE',
        'TAX',
        'DEPOSIT',
        'WITHDRAWAL',
        'SPLIT',
        'BONUS',
        'TRANSFER_IN',
        'TRANSFER_OUT'
      )
    ),

  quantity_micros INTEGER
    CHECK (
      quantity_micros IS NULL
      OR quantity_micros >= 0
    ),

  price_paise INTEGER
    CHECK (
      price_paise IS NULL
      OR price_paise >= 0
    ),

  gross_amount_paise INTEGER
    CHECK (
      gross_amount_paise IS NULL
      OR gross_amount_paise >= 0
    ),

  fees_paise INTEGER NOT NULL DEFAULT 0
    CHECK (fees_paise >= 0),

  taxes_paise INTEGER NOT NULL DEFAULT 0
    CHECK (taxes_paise >= 0),

  net_amount_paise INTEGER,

  -- Signed cash ledger impact on the portfolio.
  -- Positive = cash entering; negative = cash leaving.
  cash_effect_paise INTEGER NOT NULL,

  currency TEXT NOT NULL DEFAULT 'INR',

  exchange_rate_micros INTEGER NOT NULL DEFAULT 1000000
    CHECK (exchange_rate_micros > 0),

  executed_at INTEGER NOT NULL,
  settlement_date TEXT,

  external_reference TEXT,
  notes TEXT,

  created_at INTEGER NOT NULL,

  FOREIGN KEY (portfolio_id)
    REFERENCES portfolios(id)
    ON DELETE CASCADE,

  FOREIGN KEY (account_id)
    REFERENCES portfolio_accounts(id)
    ON DELETE SET NULL,

  FOREIGN KEY (security_id)
    REFERENCES securities(id)
    ON DELETE RESTRICT,

  FOREIGN KEY (investment_case_id)
    REFERENCES investment_cases(id)
    ON DELETE SET NULL,

  FOREIGN KEY (proposal_id)
    REFERENCES trade_proposals(id)
    ON DELETE RESTRICT,

  CHECK (
    type NOT IN (
      'BUY',
      'SELL',
      'BONUS',
      'TRANSFER_IN',
      'TRANSFER_OUT'
    )
    OR (
      security_id IS NOT NULL
      AND quantity_micros IS NOT NULL
      AND quantity_micros > 0
    )
  ),

  CHECK (
    type NOT IN ('BUY', 'SELL')
    OR (
      price_paise IS NOT NULL
      AND price_paise >= 0
    )
  ),

  CHECK (
    type NOT IN (
      'DEPOSIT',
      'WITHDRAWAL',
      'DIVIDEND',
      'INTEREST',
      'FEE',
      'TAX'
    )
    OR (
      gross_amount_paise IS NOT NULL
      AND gross_amount_paise >= 0
    )
  )
) STRICT;

CREATE INDEX transactions_portfolio_date_idx
  ON transactions(portfolio_id, executed_at DESC);
CREATE INDEX transactions_security_date_idx
  ON transactions(security_id, executed_at DESC);
CREATE INDEX transactions_investment_case_idx
  ON transactions(investment_case_id);
CREATE INDEX transactions_proposal_idx ON transactions(proposal_id);
CREATE INDEX transactions_account_idx
  ON transactions(account_id);

-- ---------------------------------------------------------------------------
-- Daily close / mark-to-market prices
-- ---------------------------------------------------------------------------
CREATE TABLE market_prices (
  security_id TEXT NOT NULL,
  price_date TEXT NOT NULL,

  price_paise INTEGER NOT NULL
    CHECK (price_paise >= 0),

  currency TEXT NOT NULL DEFAULT 'INR',
  source TEXT,

  captured_at INTEGER NOT NULL,

  PRIMARY KEY (security_id, price_date),

  FOREIGN KEY (security_id)
    REFERENCES securities(id)
    ON DELETE CASCADE
) STRICT;

CREATE INDEX market_prices_date_idx
  ON market_prices(security_id, price_date DESC);

-- ---------------------------------------------------------------------------
-- Equity research runs (DB-backed; replaces research/<slug>/<ts>/ folders)
-- ---------------------------------------------------------------------------
CREATE TABLE research_runs (
  id TEXT PRIMARY KEY,

  slug TEXT NOT NULL,
  run_key TEXT NOT NULL,

  workflow TEXT NOT NULL
    CHECK (
      workflow IN (
        'single_stock',
        'named_comparison',
        'broad_universe'
      )
    ),

  status TEXT NOT NULL DEFAULT 'IN_PROGRESS'
    CHECK (
      status IN (
        'DRAFT',
        'IN_PROGRESS',
        'COMPLETED',
        'BLOCKED',
        'ABANDONED'
      )
    ),

  title TEXT,
  universe_or_company TEXT NOT NULL,
  horizon_text TEXT NOT NULL,
  horizon_months INTEGER
    CHECK (
      horizon_months IS NULL
      OR horizon_months > 0
    ),

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

CREATE INDEX research_runs_slug_idx
  ON research_runs(slug, created_at DESC);
CREATE INDEX research_runs_status_idx
  ON research_runs(status, updated_at DESC);
CREATE INDEX research_runs_cutoff_idx
  ON research_runs(cutoff_at DESC);

-- ---------------------------------------------------------------------------
-- Names under study in a research run
-- ---------------------------------------------------------------------------
CREATE TABLE research_run_securities (
  id TEXT PRIMARY KEY,

  research_run_id TEXT NOT NULL,
  security_id TEXT,

  symbol TEXT NOT NULL,
  exchange TEXT,

  role TEXT NOT NULL DEFAULT 'SUBJECT'
    CHECK (
      role IN (
        'SUBJECT',
        'PEER',
        'BENCHMARK',
        'NEAR_MISS',
        'EXCLUDED'
      )
    ),

  sort_order INTEGER NOT NULL DEFAULT 0,
  notes TEXT,

  created_at INTEGER NOT NULL,

  FOREIGN KEY (research_run_id)
    REFERENCES research_runs(id)
    ON DELETE CASCADE,

  FOREIGN KEY (security_id)
    REFERENCES securities(id)
    ON DELETE SET NULL,

  UNIQUE (research_run_id, symbol, role)
) STRICT;

CREATE INDEX research_run_securities_run_idx
  ON research_run_securities(research_run_id, sort_order);
CREATE INDEX research_run_securities_security_idx
  ON research_run_securities(security_id);

-- ---------------------------------------------------------------------------
-- Append-only evidence ledger (sources, calcs, decisions)
-- ---------------------------------------------------------------------------
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
    REFERENCES research_runs(id)
    ON DELETE CASCADE,

  FOREIGN KEY (security_id)
    REFERENCES securities(id)
    ON DELETE SET NULL,

  CHECK (seq > 0),

  UNIQUE (research_run_id, seq)
) STRICT;

CREATE INDEX research_evidence_run_seq_idx
  ON research_evidence(research_run_id, seq);
CREATE INDEX research_evidence_run_type_idx
  ON research_evidence(research_run_id, record_type);
CREATE INDEX research_evidence_symbol_idx
  ON research_evidence(research_run_id, symbol);

-- ---------------------------------------------------------------------------
-- Bridge: finished research → portfolio workflows
-- ---------------------------------------------------------------------------
CREATE TABLE research_portfolio_links (
  id TEXT PRIMARY KEY,

  research_run_id TEXT NOT NULL,
  portfolio_id TEXT NOT NULL,
  investment_case_id TEXT,

  link_role TEXT NOT NULL DEFAULT 'ADMISSION'
    CHECK (
      link_role IN (
        'ADMISSION',
        'CONTEXT',
        'REBALANCE_INPUT',
        'THESIS_VALIDATION'
      )
    ),

  notes TEXT,
  created_at INTEGER NOT NULL,

  FOREIGN KEY (research_run_id)
    REFERENCES research_runs(id)
    ON DELETE CASCADE,

  FOREIGN KEY (portfolio_id)
    REFERENCES portfolios(id)
    ON DELETE CASCADE,

  FOREIGN KEY (investment_case_id)
    REFERENCES investment_cases(id)
    ON DELETE SET NULL,

  UNIQUE (
    research_run_id,
    portfolio_id,
    link_role,
    investment_case_id
  )
) STRICT;

CREATE INDEX research_portfolio_links_run_idx
  ON research_portfolio_links(research_run_id);
CREATE INDEX research_portfolio_links_portfolio_idx
  ON research_portfolio_links(portfolio_id);
CREATE INDEX research_portfolio_links_case_idx
  ON research_portfolio_links(investment_case_id);

-- Mark all migrations as applied (matches migrate.py versions 1–4).
INSERT INTO schema_migrations (version, name, applied_at) VALUES
  (1, 'create_portfolio_schema', CAST(strftime('%s', 'now') AS INTEGER) * 1000),
  (2, 'create_research_schema', CAST(strftime('%s', 'now') AS INTEGER) * 1000),
  (3, 'create_companies_and_link_securities', CAST(strftime('%s', 'now') AS INTEGER) * 1000),
  (4, 'add_trade_proposals', CAST(strftime('%s', 'now') AS INTEGER) * 1000);

COMMIT;

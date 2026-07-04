"""Database schema DDL.

Deliberately portable SQL: TEXT / REAL / INTEGER types and
``CREATE TABLE IF NOT EXISTS`` work identically on SQLite and PostgreSQL.
Full documentation of every column lives in DATABASE_SCHEMA.md.
"""

COMPANIES = """
CREATE TABLE IF NOT EXISTS companies (
    id                 INTEGER PRIMARY KEY,
    nse_symbol         TEXT NOT NULL UNIQUE,
    company_name       TEXT,
    bse_symbol         TEXT,
    isin               TEXT,
    mc_sc_id           TEXT,
    mc_url             TEXT,
    sector             TEXT,
    industry           TEXT,
    business_summary   TEXT,
    products_services  TEXT,
    major_clients      TEXT,
    order_book         TEXT,
    website            TEXT,
    email              TEXT,
    address            TEXT,
    phone              TEXT,
    registrar          TEXT,
    management         TEXT,
    listed_indices     TEXT,
    static_updated_at  TEXT,
    dynamic_updated_at TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
)
"""

COMPANY_INDICES = """
CREATE TABLE IF NOT EXISTS company_indices (
    company_id  INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    index_key   TEXT NOT NULL,
    index_name  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (company_id, index_key)
)
"""

MARKET_DATA = """
CREATE TABLE IF NOT EXISTS market_data (
    company_id         INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    market_cap_cr      REAL,
    price              REAL,
    pe                 REAL,
    pb                 REAL,
    industry_pe        REAL,
    dividend_yield     REAL,
    book_value         REAL,
    eps_ttm            REAL,
    face_value         REAL,
    week52_high        REAL,
    week52_low         REAL,
    shares_outstanding REAL,
    updated_at         TEXT NOT NULL
)
"""

PERIOD_RESULTS = """
CREATE TABLE IF NOT EXISTS period_results (
    company_id   INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    period_type  TEXT NOT NULL,
    period_label TEXT NOT NULL,
    revenue      REAL,
    other_income REAL,
    total_income REAL,
    expenditure  REAL,
    interest     REAL,
    tax          REAL,
    net_profit   REAL,
    basic_eps    REAL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (company_id, period_type, period_label)
)
"""

SHAREHOLDING = """
CREATE TABLE IF NOT EXISTS shareholding (
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    category   TEXT NOT NULL,
    percent    REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (company_id, category)
)
"""

SCRAPE_RUNS = """
CREATE TABLE IF NOT EXISTS scrape_runs (
    id                INTEGER PRIMARY KEY,
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    indices_fetched   INTEGER,
    constituents_seen INTEGER,
    it_companies      INTEGER,
    companies_scraped INTEGER,
    companies_failed  INTEGER,
    requests_made     INTEGER,
    notes             TEXT
)
"""

SCRAPE_ERRORS = """
CREATE TABLE IF NOT EXISTS scrape_errors (
    id           INTEGER PRIMARY KEY,
    run_id       INTEGER REFERENCES scrape_runs(id) ON DELETE CASCADE,
    nse_symbol   TEXT,
    company_name TEXT,
    stage        TEXT,
    message      TEXT,
    occurred_at  TEXT NOT NULL
)
"""

ALL_TABLES: list[str] = [
    COMPANIES,
    COMPANY_INDICES,
    MARKET_DATA,
    PERIOD_RESULTS,
    SHAREHOLDING,
    SCRAPE_RUNS,
    SCRAPE_ERRORS,
]

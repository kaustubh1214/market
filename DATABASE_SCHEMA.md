# Database Schema

SQLite by default (`data/scraper.db`); identical DDL runs on PostgreSQL.
Schema source of truth: [`scraper/db/schema.py`](scraper/db/schema.py).
All timestamps are UTC strings in `YYYY-MM-DD HH:MM:SS` format.

## Entity overview

```
companies 1 ──────* company_indices
    │ 1
    ├────1 market_data
    ├────* period_results        (quarterly + annual rows)
    └────* shareholding

scrape_runs 1 ────* scrape_errors
```

## Tables

### `companies` — one row per company (keyed by NSE symbol)

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Surrogate key |
| `nse_symbol` | TEXT UNIQUE | NSE ticker, the natural key (e.g. `TCS`) |
| `company_name` | TEXT | Name as reported by Moneycontrol |
| `bse_symbol` | TEXT | BSE scrip code (e.g. `532540`), when listed |
| `isin` | TEXT | ISIN (cross-checked NSE ↔ Moneycontrol) |
| `mc_sc_id` | TEXT | Moneycontrol internal id (used by its APIs) |
| `mc_url` | TEXT | Moneycontrol company page URL |
| `sector` | TEXT | Moneycontrol sector (e.g. `Software & IT Services`) |
| `industry` | TEXT | Moneycontrol sub-sector (e.g. `IT Services & Consulting`) |
| `business_summary` | TEXT | "About the Company" text |
| `products_services` | TEXT | Best-effort extraction from the summary |
| `major_clients` | TEXT | Best-effort extraction from the summary |
| `order_book` | TEXT | Best-effort extraction from the summary |
| `website` | TEXT | Company website |
| `email` | TEXT | Investor-relations email |
| `address` | TEXT | Registered office (single joined string) |
| `phone` | TEXT | Registered office phone |
| `registrar` | TEXT | Share registrar name |
| `management` | TEXT | `"Name (Designation); …"` |
| `listed_indices` | TEXT | Reserved (memberships live in `company_indices`) |
| `static_updated_at` | TEXT | Last static-profile refresh (drives the cache) |
| `dynamic_updated_at` | TEXT | Last dynamic-data refresh |
| `created_at` / `updated_at` | TEXT | Row lifecycle timestamps |

### `company_indices` — NSE index membership (replaced per run)

| Column | Type | Description |
|---|---|---|
| `company_id` | INTEGER FK | → `companies.id` (cascade delete) |
| `index_key` | TEXT | Registry key, e.g. `nifty_it` |
| `index_name` | TEXT | Display name, e.g. `Nifty IT` |
| `updated_at` | TEXT | |

PK: `(company_id, index_key)`

### `market_data` — current market snapshot (one row per company)

| Column | Type | Description |
|---|---|---|
| `company_id` | INTEGER PK/FK | → `companies.id` |
| `market_cap_cr` | REAL | Market cap, Rs. crore |
| `price` | REAL | Last traded price |
| `pe` / `pb` / `industry_pe` | REAL | Valuation ratios |
| `dividend_yield` | REAL | Percent |
| `book_value` | REAL | Rs. per share |
| `eps_ttm` | REAL | Trailing-twelve-month EPS |
| `face_value` | REAL | Rs. |
| `week52_high` / `week52_low` | REAL | 52-week range |
| `shares_outstanding` | REAL | Share count |
| `updated_at` | TEXT | |

### `period_results` — quarterly and annual P&L rows

| Column | Type | Description |
|---|---|---|
| `company_id` | INTEGER FK | → `companies.id` |
| `period_type` | TEXT | `Q` (quarter) or `Y` (fiscal year) |
| `period_label` | TEXT | Moneycontrol label, e.g. `Mar '26` |
| `revenue` | REAL | Net sales / income from operations, Rs. crore |
| `other_income` | REAL | |
| `total_income` | REAL | |
| `expenditure` | REAL | Total expenditure |
| `interest` | REAL | |
| `tax` | REAL | |
| `net_profit` | REAL | Net profit/(loss) for the period |
| `basic_eps` | REAL | Rs. |
| `updated_at` | TEXT | |

PK: `(company_id, period_type, period_label)`.
Ordering is derived by parsing `period_label` (see
`utils/helpers.py::period_sort_key`) — never rely on insertion order.

### `shareholding` — latest shareholding pattern (replaced per refresh)

| Column | Type | Description |
|---|---|---|
| `company_id` | INTEGER FK | → `companies.id` |
| `category` | TEXT | `Promoter` / `FII` / `DII` / `Public` / `Others` |
| `percent` | REAL | Percent of equity |
| `updated_at` | TEXT | |

PK: `(company_id, category)`

### `scrape_runs` — one row per execution

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Run id |
| `started_at` / `finished_at` | TEXT | |
| `indices_fetched` | INTEGER | NSE indices downloaded |
| `constituents_seen` | INTEGER | Unique symbols across all indices |
| `it_companies` | INTEGER | After IT filtering |
| `companies_scraped` | INTEGER | Succeeded |
| `companies_failed` | INTEGER | Failed |
| `requests_made` | INTEGER | HTTP requests issued |
| `notes` | TEXT | `completed` or `interrupted` |

### `scrape_errors` — failures captured during runs

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | |
| `run_id` | INTEGER FK | → `scrape_runs.id` |
| `nse_symbol` / `company_name` | TEXT | Affected company |
| `stage` | TEXT | `resolve` / `pricefeed` / `quarterly` / `yearly` / `profile` / `unexpected` |
| `message` | TEXT | Error detail |
| `occurred_at` | TEXT | |

## Migrating to PostgreSQL

1. `pip install psycopg2-binary` (uncomment it in `requirements.txt`).
2. Set `DATABASE_URL=postgresql://user:password@host:5432/dbname` in `.env`.
3. Run the scraper — `create_schema()` creates all tables on first use.

Notes:
- `INTEGER PRIMARY KEY` auto-increments on SQLite; on PostgreSQL prefer
  changing the PK columns in `schema.py` to `SERIAL PRIMARY KEY` (or insert
  explicit ids). This is the only DDL adjustment needed.
- Parameter placeholders are translated automatically (`?` → `%s`) by
  `db/connection.py`; repository code never changes.
- To migrate existing data, export SQLite tables to CSV
  (`sqlite3 data/scraper.db ".mode csv" ...`) and `COPY` them into PostgreSQL.

# Architecture

## Layered design

```
                 ┌────────────────────────────────────────────┐
                 │                 main.py (CLI)              │
                 └──────────────────────┬─────────────────────┘
                                        │
                 ┌──────────────────────▼─────────────────────┐
                 │        scraper/pipeline.py (orchestrator)  │
                 └──┬───────────┬───────────┬───────────┬─────┘
                    │           │           │           │
        ┌───────────▼──┐ ┌──────▼─────┐ ┌───▼───────┐ ┌─▼──────────┐
        │ scraping/    │ │ parsing/   │ │ db/       │ │ exporters/ │
        │ HTTP + sites │ │ HTML/JSON  │ │ SQL       │ │ xlsx / csv │
        └───────┬──────┘ └──────┬─────┘ └───┬───────┘ └─┬──────────┘
                │               │           │           │
        ┌───────▼───────────────▼───────────▼───────────▼──────────┐
        │   models/ (dataclasses)  ·  config/  ·  utils/           │
        └──────────────────────────────────────────────────────────┘
```

| Package | Responsibility | Key rule |
|---|---|---|
| `scraper/config` | Settings from env vars; NSE index registry | No I/O besides reading `.env` |
| `scraper/models` | Typed dataclasses passed between layers | No behaviour, only data |
| `scraper/scraping` | HTTP client + site fetchers | Returns raw bytes/JSON — **never parses HTML** |
| `scraper/parsing` | HTML/JSON → dataclasses | Pure functions — **never does I/O** |
| `scraper/db` | Connection, DDL, repositories | The only place SQL exists |
| `scraper/exporters` | Excel workbook, CSV files | Reads dicts, never queries the DB itself |
| `scraper/utils` | Logging setup, checkpoint, tiny pure helpers | No project imports besides config |
| `scraper/pipeline.py` | Wires everything together for a run | The only module that imports across layers |

The separation means each layer is unit-testable in isolation: parsers are
tested with HTML snippets (no network), repositories with a temp SQLite file
(no scraping), and fetchers can be swapped without touching business logic.

## Static vs dynamic data

The scraper distinguishes two data families with different lifecycles:

- **Static** (`CompanyProfile`): business summary, website, address,
  management, registrar, identifiers. Sourced from the company profile page
  (1 MB+ per fetch). Cached in the `companies` table with a
  `static_updated_at` timestamp and re-fetched only when missing or older
  than `STATIC_REFRESH_DAYS`.
- **Dynamic** (`MarketData`, `PeriodResult`, `ShareholdingEntry`): market
  snapshot, quarterly/annual results. Sourced from lightweight JSON APIs and
  refreshed on **every** run; `dynamic_updated_at` records the last refresh.

A company whose profile page exists but genuinely lacks a business summary is
treated as "never scraped statically", so it is retried each run — the cost
is one page fetch and it self-heals when Moneycontrol adds the text.

## Design decisions

### Why `curl_cffi` instead of `requests`?
Moneycontrol's HTML pages sit behind an Akamai edge that fingerprints the TLS
handshake. Plain `requests`/`urllib` receive HTTP 403 regardless of headers.
`curl_cffi` impersonates Chrome's TLS stack and passes. The JSON APIs
(`priceapi`, `appfeeds`) are less strict but use the same client for
uniform retry/rate-limit behaviour.

### Why JSON APIs for financials instead of HTML tables?
Moneycontrol's financials pages are a Next.js app; the visible tables are
rendered from JSON. Scraping the underlying feeds
(`appfeeds.moneycontrol.com/jsonapi/stocks/…`) is faster (no 1 MB HTML), far
more stable against redesigns, and returns clean numeric strings.

### Why hand-rolled SQL instead of an ORM?
The schema is small (7 tables) and the central requirement — *update only
changed fields* — needs explicit read-diff-update logic anyway. Avoiding
SQLAlchemy keeps the dependency footprint small. Portability is preserved by
writing dialect-neutral SQL; `db/connection.py` translates parameter
placeholders for PostgreSQL.

### Change detection
Every repository upsert follows the same pattern:

1. `SELECT` the existing row.
2. Diff each field; **`None` never overwrites a stored value** (a temporarily
   missing field on the site must not erase good data).
3. `UPDATE` only the changed columns (or `INSERT` when new).

Consequence: rerunning the scraper against unchanged sources performs zero
writes, and `updated_at` timestamps are trustworthy.

### Resume capability
`utils/checkpoint.py` persists the set of completed symbols to
`data/checkpoint.json` after each company. On start-up an existing checkpoint
is loaded automatically (opt out with `--fresh`); after a fully successful
run it is deleted. Crash-safety comes from writing the file after every
company, not at the end.

### Error philosophy
A failure in one company never aborts the run. Failures are recorded as
`ScrapeError` rows (DB + Excel "Errors & Skipped" sheet + log). Only the
company-level "resolve identity" and "price feed" steps are fatal *for that
company*; missing financials or profile sections merely produce
missing-field reports.

## Extensibility

- **New NSE index** → one `IndexDefinition` line in `scraper/config/indices.py`.
- **New scraped field** → extend the relevant dataclass, parser, DDL column
  and export sheet (see HANDOFF.md for the step-by-step recipe).
- **New data source (another website)** → add a fetcher module under
  `scraper/scraping/` and a parser under `scraper/parsing/`; the pipeline
  composes them. Nothing else changes.
- **PostgreSQL** → set `DATABASE_URL`, install `psycopg2-binary`. See
  DATABASE_SCHEMA.md.

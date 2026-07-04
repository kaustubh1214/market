# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/); versioning: SemVer.

## [1.0.0] — 2026-07-04

### Added
- Initial release of the Moneycontrol IT scraper.
- NSE index discovery via archives CSVs: Nifty IT, Nifty Midcap 150,
  Nifty MidSmallcap 400, Nifty Smallcap 250, Nifty LargeMidcap 250,
  Nifty Midcap Select (extensible registry in `scraper/config/indices.py`).
- IT-sector filtering on the NSE `Industry` column (Nifty IT bypasses the
  filter as an all-IT index).
- Moneycontrol scraping:
  - symbol→`sc_id` resolution via autosuggest with ISIN-based matching,
  - price feed (market cap, P/E, P/B, industry P/E, dividend yield, book
    value, EPS TTM, face value, 52-week range, shares outstanding),
  - quarterly and annual results feeds (revenue, other income, interest,
    tax, net profit, basic EPS per period),
  - company profile page (business summary, website, email, phone, address,
    management, registrar, BSE code, ISIN, shareholding pattern),
  - best-effort extraction of products & services, major clients and order
    book from the profile text.
- Static/dynamic split with `STATIC_REFRESH_DAYS` cache (default 30 days)
  and per-company `static_updated_at` / `dynamic_updated_at` timestamps.
- SQLite database (PostgreSQL-ready) with field-level change detection:
  reruns against unchanged data perform zero writes; `None` never erases
  stored values.
- Resume capability: per-company checkpoint file survives crashes/Ctrl+C.
- Polite HTTP client (curl_cffi Chrome impersonation, rate limiting with
  jitter, exponential-backoff retries, browser-profile rotation on 403).
- Formatted Excel export (10 sheets incl. Errors & Skipped and Execution
  Summary) and optional CSV export.
- Per-run DEBUG log files; run statistics persisted to the database.
- Pytest suite (48 tests) covering helpers, parsers, config and repositories.
- Documentation: README, ARCHITECTURE, DATABASE_SCHEMA, SCRAPER_FLOW,
  CONFIGURATION, HANDOFF.

### Known limitations
- Products & services / major clients / order book depend on the wording of
  Moneycontrol's profile text (no structured source exists).
- Shareholding pattern is the summary breakdown (Promoter/FII/DII/Public/
  Others), not the full top-holders table.
- Financial figures are as published on Moneycontrol (standalone vs
  consolidated follows Moneycontrol's default for each company).

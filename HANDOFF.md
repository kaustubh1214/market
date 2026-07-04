# HANDOFF — Developer Onboarding

Everything a developer needs to continue this project without further
explanation. Read this first; the other docs go deeper per topic.

## 1. What this project does

Scrapes Moneycontrol for **IT companies that belong to configured NSE
indices** and produces: a SQLite database (PostgreSQL-ready), a formatted
Excel workbook per run, optional CSVs, and per-run log files. Static profile
data is cached (default 30 days); market/financial data refreshes every run.

Verified working against the live sites on 2026-07-04.

## 2. Project structure

```
D:\market
├── main.py                     # CLI entry point (argparse)
├── requirements.txt
├── .env.example                # copy to .env to configure
├── pytest.ini
├── data/                       # SQLite DB + checkpoint.json (created at runtime)
├── exports/                    # Excel/CSV output (created at runtime)
├── logs/                       # one log file per run
├── scraper/
│   ├── pipeline.py             # ORCHESTRATOR — start reading here
│   ├── config/
│   │   ├── settings.py         # env-driven Settings dataclass
│   │   └── indices.py          # NSE index registry (add indices here)
│   ├── models/company.py       # all dataclasses (static vs dynamic families)
│   ├── scraping/
│   │   ├── http_client.py      # curl_cffi client: rate limit, retries, 403 rotation
│   │   ├── nse_indices.py      # NSE constituents CSVs
│   │   └── moneycontrol.py     # MC endpoints: autosuggest, pricefeed, results, page
│   ├── parsing/
│   │   ├── company_page.py     # profile HTML → CompanyPageData (+ shareholding)
│   │   ├── financials.py       # pricefeed/results JSON → MarketData/PeriodResult
│   │   └── text_extract.py     # products/clients/order-book heuristics
│   ├── db/
│   │   ├── connection.py       # SQLite/PostgreSQL wrapper (placeholder translation)
│   │   ├── schema.py           # portable DDL
│   │   └── repository.py       # upserts with field-level change detection
│   ├── exporters/
│   │   ├── excel_exporter.py   # 10-sheet formatted workbook
│   │   └── csv_exporter.py
│   └── utils/
│       ├── helpers.py          # clean_text, parse_number, period_sort_key
│       ├── logging_setup.py
│       └── checkpoint.py       # resume-after-interruption
└── tests/                      # pytest suite (48 tests, no network needed)
```

## 3. How data flows (NSE → Moneycontrol → DB → Excel)

1. **NSE archives CSVs** (`archives.nseindia.com/content/indices/ind_*.csv`)
   give constituents per index: name, symbol, NSE industry, ISIN.
2. Constituents are merged by symbol; non-IT companies are dropped
   (`Industry == "Information Technology"`, except Nifty IT which is all-IT).
3. **Moneycontrol autosuggest** maps NSE symbol → `sc_id` + company URL.
   ⚠️ The suggest API is fuzzy — always match by **ISIN**, never take the
   first hit (querying "COFORGE" returns Bharat Forge first!).
4. **Dynamic** every run:
   - `priceapi.moneycontrol.com/pricefeed/nse/equitycash/{sc_id}` → market
     cap, ratios, sector/industry, BSE id, ISIN.
   - `appfeeds.moneycontrol.com/jsonapi/stocks/{quarterly|yearly}_results_responsive`
     → per-period P&L (note: `type_format` param equals the kind, e.g.
     `quarterly`).
5. **Static** when stale (>30 days) or missing: the classic company page HTML →
   business summary, hidden company-info JSON (website/address/management/…)
   and inline shareholding JSON (`var summary_jsn = …`).
6. Repositories upsert with per-field diffing; exports read back from the DB.

## 4. Caching strategy

- `companies.static_updated_at` + `business_summary IS NOT NULL` decide
  whether the profile page is fetched (`CompanyRepository.static_age_days`,
  `ScraperPipeline._static_is_stale`).
- Dynamic data has no cache — every run refreshes it and touches
  `dynamic_updated_at`.
- Change detection: upserts never write unchanged values, and incoming
  `None` never erases stored data.

## 5. Things that will bite you if you don't know them

- **HTTP 403 everywhere?** Moneycontrol's Akamai edge fingerprints TLS.
  Only `curl_cffi` with `impersonate="chrome"` (or edge/safari) passes —
  plain `requests` will always 403 on the www host. The client rotates
  profiles automatically after a 403.
- **Period ordering**: labels like `Mar '26` don't sort lexically and DB
  insertion order is not chronological across runs. Always order via
  `period_sort_key()` (already done in `fetch_period_results`).
- **"Data is not Available"**: Moneycontrol renders this literal placeholder
  as the business summary for some smaller companies; the parser converts it
  to `None`, which means such companies re-fetch their profile page every
  run (self-healing by design).
- **Products/Clients/Order book** are *not* structured fields on
  Moneycontrol. `text_extract.py` pulls matching sentences out of the
  summary text; empty is normal and reported under missing fields.
- **NSE CSV names** occasionally change (e.g. Midcap Select is
  `ind_niftymidcapselect_list.csv` — note the underscore). If an index 404s,
  check the current filename on niftyindices.com.
- **Python 3.10+ required** (dataclasses + `X | None` unions); developed on 3.14.

## 6. How to…

### Add a new NSE index
`scraper/config/indices.py` → add an `IndexDefinition`. Done. (Flag
`all_constituents_are_it=True` only for pure-IT indices.)

### Add a new scraped field
1. Add it to the right dataclass in `models/company.py`
   (static → `CompanyProfile`, dynamic → `MarketData`/`PeriodResult`).
2. Populate it in the parser (`parsing/…`) — for profile data also wire it
   in `pipeline._build_profile`.
3. Add the column in `db/schema.py` (and `ALTER TABLE` your existing DB, or
   delete `data/scraper.db` to recreate).
4. Repositories pick up new dataclass fields automatically (they introspect
   `dataclasses.fields`) — no repository change needed.
5. Add it to the relevant sheet in `exporters/excel_exporter.py`.
6. Extend a test in `tests/`.

### Add another financial website as a source
Create `scraping/<site>.py` (fetch only) + `parsing/<site>.py` (parse only),
then call them from `pipeline.scrape_company` and store via existing or new
repositories. The HTTP client is site-agnostic.

### Switch to PostgreSQL
See DATABASE_SCHEMA.md → "Migrating to PostgreSQL".

## 7. Troubleshooting failures

1. **Read the log** — `logs/run_….log` has DEBUG detail incl. every retry.
2. **Check the Errors & Skipped sheet** — stage tells you where it died:
   `resolve` (autosuggest mismatch → check ISIN in the NSE CSV),
   `pricefeed` (bad `sc_id` or delisted), `quarterly`/`yearly` (no
   financials published), `profile` (page layout change → fix
   `parsing/company_page.py`).
3. **`scrape_errors` table** keeps the full history across runs.
4. **Layout changed?** Save the page (`MoneycontrolScraper.fetch_company_page`)
   to a file and adjust the three independent extractors in
   `parsing/company_page.py`; each has its own test in
   `tests/test_parsers.py`.
5. **Everything 403s suddenly**: bump `REQUEST_DELAY_SECONDS`, try again
   later (IP throttling), or add newer impersonation profiles to
   `IMPERSONATE_PROFILES` in `http_client.py` (curl_cffi ships new ones in
   each release).
6. **Interrupted run**: just rerun — the checkpoint resumes automatically.
   `--fresh` discards it.

## 8. Development workflow

```bash
pip install -r requirements.txt
python -m pytest                  # 48 tests, no network
python main.py --dry-run          # discovery only (network: NSE)
python main.py --symbols TCS      # single company end-to-end
python main.py                    # full run (~27 companies, ~5–10 min)
```

Conventions: type hints everywhere, docstrings on every module/class/public
function, parsers are pure functions, scraping never parses, SQL only in
`db/`, all timestamps UTC.

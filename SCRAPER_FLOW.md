# Scraper Flow

End-to-end description of one execution (`python main.py`). Implementation:
[`scraper/pipeline.py`](scraper/pipeline.py).

## 0. Bootstrap

1. `main.py` parses CLI flags, loads `Settings` (env + `.env`), configures
   logging (`logs/run_….log`), opens the database and creates the schema if
   missing.
2. A `scrape_runs` row is inserted; an existing checkpoint from an
   interrupted run is loaded (unless `--fresh`).

## 1. Index discovery (NSE)

For every configured index (`scraper/config/indices.py`) the constituents CSV
is downloaded from the NSE archives:

```
https://archives.nseindia.com/content/indices/ind_niftyitlist.csv
Company Name, Industry, Symbol, Series, ISIN Code
```

Rows are merged **by NSE symbol**; a company present in several indices keeps
the union of its index memberships.

## 2. IT filtering

A constituent is kept when **either**:

- it belongs to an index flagged `all_constituents_are_it` (Nifty IT), or
- its NSE `Industry` column matches `IT_INDUSTRY_VALUES`
  (default: `Information Technology`).

Everything else is dropped before any Moneycontrol traffic happens. With the
default six indices this reduces ~500 constituents to ~27 IT companies.

## 3. Per-company scraping (Moneycontrol)

For each IT company, in order:

### 3.1 Identity resolution — `resolve`
```
GET https://www.moneycontrol.com/mccode/common/autosuggestion_solr.php
        ?classic=true&query={NSE_SYMBOL}&type=1&format=json
```
The autosuggest API is fuzzy (querying `COFORGE` returns *Bharat Forge*
first), so candidates are matched by **ISIN** (from the NSE CSV) embedded in
the display name, falling back to an exact NSE-symbol token match. Yields the
Moneycontrol `sc_id` and company page URL. Failure here skips the company.

### 3.2 Dynamic data — every run
```
GET https://priceapi.moneycontrol.com/pricefeed/nse/equitycash/{sc_id}
```
→ market cap, price, P/E, P/B, industry P/E, dividend yield, book value,
EPS (TTM), face value, 52-week range, shares outstanding — plus sector,
industry, BSE code and ISIN used to enrich the profile.

```
GET https://appfeeds.moneycontrol.com/jsonapi/stocks/quarterly_results_responsive
        ?sc_id={sc_id}&type_format=quarterly&start=0&limit=8
GET https://appfeeds.moneycontrol.com/jsonapi/stocks/yearly_results_responsive
        ?sc_id={sc_id}&type_format=yearly&start=0&limit=8
```
→ per-period P&L rows (revenue, other income, interest, tax, net profit,
basic EPS). Rows whose numeric fields are all missing are dropped.

### 3.3 Static data — only when stale
The company profile page is fetched **only** when the cached profile is
missing its business summary or `static_updated_at` is older than
`STATIC_REFRESH_DAYS`:

```
GET {company_page_url}   (classic Moneycontrol page, ~1 MB HTML)
```

Three independent extractions (`scraper/parsing/company_page.py`):
1. `#company_info .morepls_cnt` → business summary (a literal
   "Data is not Available" placeholder is treated as missing);
2. a hidden JSON blob → website, email, phone, address, management,
   registrar, BSE code, ISIN;
3. inline `var summary_jsn = '{"Promoter":71.77,…}'` → shareholding pattern.

The business summary is then run through keyword heuristics
(`parsing/text_extract.py`) to extract *Products & Services*, *Major
Clients* and *Order Book* sentences when present.

### 3.4 Persistence
All data is upserted with field-level change detection (see
ARCHITECTURE.md); `dynamic_updated_at` is always touched,
`static_updated_at` only when the profile page was fetched. The symbol is
checkpointed as done.

## 4. Export

After the loop, data for all successfully processed symbols is read back
from the DB and written to:

- **Excel** — `exports/moneycontrol_it_….xlsx` with sheets: Company List,
  Company Profile, Financial Data (market snapshot + latest FY), Quarterly
  Results (last 3 quarters per company), Shareholding, Products & Services,
  Clients, Order Book, Errors & Skipped (failures + missing fields),
  Execution Summary. Formatting: bold headers on dark blue, frozen header
  row, auto-filter, sized columns, thousands separators.
- **CSV** (optional) — `exports/csv_…/` with companies, quarterly_results,
  annual_results and shareholding files (UTF-8 BOM for Excel compatibility).

## 5. Finish

Run statistics and errors are written to `scrape_runs` / `scrape_errors`,
the checkpoint file is deleted (only on a non-interrupted run) and a summary
line is logged.

## Rate limiting, retries, resilience

- ≥ `REQUEST_DELAY_SECONDS` + random jitter between *any* two requests.
- Up to `MAX_RETRIES` retries with exponential backoff (base
  `RETRY_BACKOFF_BASE`, doubling each attempt + jitter) on 403/408/425/429/
  5xx and network errors; 404 fails fast.
- On a 403 the client rotates to another browser impersonation profile
  (chrome → edge → safari) — Akamai occasionally flags a fingerprint.
- `Ctrl+C` checkpoints progress and still writes exports for what finished;
  the next run resumes automatically.

## Failure handling per stage

| Stage | On failure |
|---|---|
| Index CSV download | Run aborts (nothing to scrape) — retried per policy first |
| `resolve` | Company skipped, error recorded |
| `pricefeed` | Company skipped, error recorded |
| `quarterly` / `yearly` | Recorded, company continues |
| `profile` | Recorded, company continues (static retried next run) |
| Anything unexpected | Caught per company, recorded as `unexpected`, run continues |

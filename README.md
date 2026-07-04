# Moneycontrol IT Scraper 🤖📈

A production-grade, modular Python bot that automatically collects data about
**IT companies listed in NSE indices** from
[Moneycontrol](https://www.moneycontrol.com).

**What the bot does, in one paragraph:** it downloads the constituents of the
configured NSE indices (Nifty IT, Nifty Midcap 150, Nifty MidSmallcap 400,
Nifty Smallcap 250, Nifty LargeMidcap 250, Nifty Midcap Select), keeps only
companies whose sector is Information Technology, then for each company
scrapes Moneycontrol for its profile (business summary, website, management,
address…), live market data (market cap, P/E, P/B, dividend yield…),
quarterly & annual financial results and shareholding pattern — and saves
everything into a local database plus a nicely formatted Excel report.

## 🚀 Quick start (after cloning)

```bash
git clone https://github.com/kaustubh1214/market.git
cd market

# 1. Install dependencies (Python 3.10+ required)
pip install -r requirements.txt

# 2. (Optional) configure — defaults work out of the box
copy .env.example .env        # Windows
# cp .env.example .env        # Linux/Mac

# 3. See which companies would be scraped (no scraping yet)
python main.py --dry-run

# 4. Run the full scrape (~27 companies, ~6 minutes)
python main.py
```

**Windows one-click:** just double-click **`run_scraper.bat`** — it runs the
full scrape and opens the exports folder when done.

Useful variants:

```bash
python main.py --limit 5              # first 5 companies only (smoke test)
python main.py --symbols TCS,INFY     # only specific NSE symbols
python main.py --csv                  # also write CSV files
python main.py --no-export           # update database only, no Excel
python main.py --fresh                # ignore interrupted-run checkpoint
python main.py --log-level DEBUG      # verbose console output
```

## 📁 Folder structure

```
market/
├── main.py                     # CLI entry point — start here
├── run_scraper.bat             # Windows one-click runner
├── requirements.txt            # Python dependencies
├── .env.example                # copy to .env to configure (optional)
│
├── scraper/                    # the bot itself (modular package)
│   ├── pipeline.py             # orchestrator: discovery → scrape → save → export
│   ├── config/
│   │   ├── settings.py         # all settings (read from .env / env vars)
│   │   └── indices.py          # NSE index registry (add new indices here)
│   ├── models/company.py       # typed dataclasses for all scraped data
│   ├── scraping/               # HTTP layer (downloads only, no parsing)
│   │   ├── http_client.py      # rate limiting, retries, browser impersonation
│   │   ├── nse_indices.py      # NSE constituents CSVs
│   │   └── moneycontrol.py     # Moneycontrol endpoints
│   ├── parsing/                # turns raw HTML/JSON into clean data
│   │   ├── company_page.py     # profile page parser
│   │   ├── financials.py       # market data + results parsers
│   │   └── text_extract.py     # products/clients/order-book heuristics
│   ├── db/                     # database layer (all SQL lives here)
│   │   ├── connection.py       # SQLite default, PostgreSQL-ready
│   │   ├── schema.py           # table definitions
│   │   └── repository.py       # smart upserts (only changed fields)
│   ├── exporters/
│   │   ├── excel_exporter.py   # formatted 10-sheet workbook
│   │   └── csv_exporter.py     # optional CSV mirror
│   └── utils/                  # logging, checkpoint/resume, helpers
│
├── tests/                      # pytest suite (48 tests, run: python -m pytest)
│
│   # created automatically on first run (not in git):
├── data/                       # SQLite database + resume checkpoint
├── exports/                    # Excel/CSV output files
└── logs/                       # one detailed log file per run
```

## ⚙️ How the bot works

```
NSE archives CSVs ──► merge constituents ──► keep IT companies only
                                                     │
                     for each company ◄──────────────┘
                     ├─ 1. resolve symbol → Moneycontrol id (matched by ISIN)
                     ├─ 2. price feed API   → market cap, P/E, P/B, yield… (every run)
                     ├─ 3. results feed API → quarterly + annual P&L      (every run)
                     ├─ 4. company page     → profile + shareholding      (only if cache stale)
                     └─ 5. save to database (only changed fields written)
                                                     │
                     Excel workbook + CSVs + logs ◄──┘
```

Key behaviours:

- **Static vs dynamic data** — profile data (summary, website, management…)
  is cached and re-scraped only when missing or older than 30 days
  (`STATIC_REFRESH_DAYS`); market data and financials refresh on **every**
  run. Both have their own "last updated" timestamps per company.
- **No duplicates** — companies are keyed by NSE symbol; every save diffs
  field-by-field and writes only what changed. Running twice in a row
  writes nothing the second time.
- **Resume after interruption** — progress is checkpointed after every
  company; if the run crashes or you press Ctrl+C, just run again and it
  continues where it stopped.
- **Polite & resilient** — delay + random jitter between requests,
  exponential-backoff retries, browser TLS impersonation (`curl_cffi`,
  required because Moneycontrol blocks plain Python HTTP clients), and
  per-company error isolation: one failed company never kills the run.

## 💾 Where the data is saved

| Location | What | When |
|---|---|---|
| `data/scraper.db` | SQLite database — companies, market data, quarterly/annual results, shareholding, run history, errors | every run (incremental) |
| `exports/moneycontrol_it_YYYYMMDD_HHMMSS.xlsx` | Formatted Excel workbook, 10 sheets | every run |
| `exports/csv_YYYYMMDD_HHMMSS/` | CSV mirror of the main tables | when `--csv` / `EXPORT_CSV=true` |
| `logs/run_YYYYMMDD_HHMMSS.log` | Full DEBUG log of the run | every run |

Excel sheets: **Company List · Company Profile · Financial Data · Quarterly
Results · Shareholding · Products & Services · Clients · Order Book ·
Errors & Skipped · Execution Summary** — with bold headers, frozen rows,
filters and number formatting, ready for business users.

### Data collected per company

| Static (cached ~30 days) | Dynamic (every run) |
|---|---|
| Company name, NSE/BSE symbols, ISIN | Market cap, price, P/E, P/B, industry P/E |
| Sector & industry | Dividend yield, book value, EPS (TTM), 52-week range |
| Business summary ("About the Company") | Last quarterly results (revenue, profit, EPS…) |
| Products & services, clients, order book¹ | Annual financials (5+ years) |
| Website, email, phone, address | Shareholding pattern (Promoter/FII/DII/Public/Others) |
| Management, registrar, Moneycontrol URL | Last-updated timestamps |

¹ Best-effort extraction from the profile text — Moneycontrol has no
structured fields for these; blank simply means the profile doesn't mention
them.

## 🧪 Tests

```bash
python -m pytest        # 48 tests, no network needed
```

## 📚 Full documentation

| File | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Layers, modules, design decisions |
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | Every table & column, PostgreSQL migration |
| [SCRAPER_FLOW.md](SCRAPER_FLOW.md) | Step-by-step flow, exact endpoints used |
| [CONFIGURATION.md](CONFIGURATION.md) | Every setting and CLI flag |
| [HANDOFF.md](HANDOFF.md) | Developer handoff: extending & troubleshooting |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

**Adding a new NSE index is one line** in
[`scraper/config/indices.py`](scraper/config/indices.py) — see
CONFIGURATION.md.

## ⚖️ Legal note

For personal research only. Respect Moneycontrol's terms of service, keep
the request rate low (defaults are conservative) and do not redistribute
scraped data commercially.

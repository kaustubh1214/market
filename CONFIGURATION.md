# Configuration

Configuration comes from **environment variables**, optionally loaded from a
`.env` file in the project root (copy `.env.example`). CLI flags override a
few settings per run. Defaults live in
[`scraper/config/settings.py`](scraper/config/settings.py).

## Environment variables

### Database

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///data/scraper.db` | `sqlite:///<path>` (relative to project root) or `postgresql://user:pass@host:port/db` (needs `psycopg2-binary`) |

### HTTP behaviour

| Variable | Default | Description |
|---|---|---|
| `REQUEST_DELAY_SECONDS` | `1.5` | Minimum delay between any two HTTP requests |
| `REQUEST_JITTER_SECONDS` | `1.0` | Extra random delay (0..N) added on top |
| `REQUEST_TIMEOUT_SECONDS` | `40` | Per-request timeout |
| `MAX_RETRIES` | `4` | Retry attempts per request (exponential backoff) |
| `RETRY_BACKOFF_BASE` | `2.0` | First retry waits this many seconds; doubles per attempt |

### Static-data caching

| Variable | Default | Description |
|---|---|---|
| `STATIC_REFRESH_DAYS` | `30` | Re-fetch the profile page only when the cached profile is older than this (or missing) |

### Index & sector selection

| Variable | Default | Description |
|---|---|---|
| `INDICES` | *(all six)* | Comma-separated index keys to restrict a run, e.g. `nifty_it,nifty_midcap_150`. Keys are defined in `scraper/config/indices.py` |
| `IT_INDUSTRY_VALUES` | `Information Technology` | NSE `Industry` values treated as IT (comma-separated, case-insensitive) |
| `IT_MC_SECTOR_VALUES` | `Software & IT Services,IT Services & Consulting` | Moneycontrol sector names treated as IT (used by `Settings.is_it_mc_sector`, available for custom filters) |

### Export

| Variable | Default | Description |
|---|---|---|
| `EXPORT_DIR` | `exports` | Output folder (relative to project root or absolute) |
| `EXPORT_EXCEL` | `true` | Write the `.xlsx` workbook |
| `EXPORT_CSV` | `false` | Also write CSV files |

### Logging

| Variable | Default | Description |
|---|---|---|
| `LOG_DIR` | `logs` | Log folder |
| `LOG_LEVEL` | `INFO` | Console level; the log **file** always captures DEBUG |

## CLI flags (`python main.py --help`)

| Flag | Effect |
|---|---|
| `--dry-run` | Fetch indices, print the IT universe, scrape nothing |
| `--symbols TCS,INFY` | Restrict to specific NSE symbols (subset of the IT universe) |
| `--limit N` | Scrape at most N companies (smoke tests) |
| `--fresh` | Discard an interrupted-run checkpoint and start over |
| `--no-export` | Update the database but skip Excel/CSV |
| `--csv` | Force CSV export for this run (overrides `EXPORT_CSV`) |
| `--log-level DEBUG` | Console verbosity for this run |

## Adding an index (recap)

Add one entry to `DEFAULT_INDICES` in `scraper/config/indices.py`:

```python
IndexDefinition(
    key="nifty_next_50",
    name="Nifty Next 50",
    csv_filename="ind_niftynext50list.csv",   # under archives.nseindia.com/content/indices/
),
```

Set `all_constituents_are_it=True` only for indices that exclusively contain
IT companies (their constituents then bypass the industry filter). Find CSV
filenames on <https://www.niftyindices.com> (each index page links its
constituents file).

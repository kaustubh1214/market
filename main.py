"""Command-line entry point for the Moneycontrol IT scraper.

Examples:
    python main.py                       # full run (all configured indices)
    python main.py --limit 5             # smoke test with 5 companies
    python main.py --symbols TCS,INFY    # only specific NSE symbols
    python main.py --fresh               # ignore an interrupted-run checkpoint
    python main.py --csv                 # also write CSV exports
    python main.py --dry-run             # list IT companies, scrape nothing
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys

from scraper.config.settings import get_settings
from scraper.db.connection import Database
from scraper.pipeline import ScraperPipeline
from scraper.utils.logging_setup import setup_logging

logger = logging.getLogger("main")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape Moneycontrol data for IT companies in NSE indices."
    )
    parser.add_argument(
        "--symbols",
        help="Comma-separated NSE symbols to scrape (subset of the IT universe).",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Scrape at most N companies (useful for smoke tests).",
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="Discard any interrupted-run checkpoint and start over.",
    )
    parser.add_argument(
        "--no-export", action="store_true",
        help="Skip Excel/CSV export (database is still updated).",
    )
    parser.add_argument(
        "--csv", action="store_true",
        help="Also write CSV exports regardless of EXPORT_CSV.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Only list the IT companies that would be scraped, then exit.",
    )
    parser.add_argument(
        "--log-level", default=None,
        help="Console log level (DEBUG/INFO/WARNING). Overrides LOG_LEVEL.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    settings = get_settings()
    if args.csv:
        settings = dataclasses.replace(settings, export_csv=True)

    log_file = setup_logging(settings.log_dir, args.log_level or settings.log_level)
    logger.info("Log file: %s", log_file)

    symbols = (
        [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else None
    )

    with Database(settings.database_url) as db:
        pipeline = ScraperPipeline(settings, db)
        if args.dry_run:
            db.create_schema()
            companies = pipeline.discover_it_companies(symbols, args.limit)
            print(f"\n{len(companies)} IT companies would be scraped:")
            for c in companies:
                print(f"  {c.nse_symbol:<12} {c.company_name:<45} "
                      f"[{', '.join(c.index_keys)}]")
            return 0

        stats = pipeline.run(
            only_symbols=symbols,
            limit=args.limit,
            fresh=args.fresh,
            export=not args.no_export,
        )
    return 1 if stats.companies_scraped == 0 and stats.companies_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

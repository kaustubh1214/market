"""Pipeline orchestrator: index discovery -> IT filter -> scrape -> export.

High-level flow for one run (details in SCRAPER_FLOW.md):

1. Fetch constituents of all configured NSE indices and merge by symbol.
2. Keep IT companies (Nifty IT members, or NSE industry == IT, or
   Moneycontrol sector == IT as a fallback).
3. Per company: resolve Moneycontrol identity, refresh dynamic data (price
   feed, quarterly + annual results, shareholding) and static data (company
   page) when stale, upserting field-by-field into the database.
4. Export the workbook / CSVs and record run statistics.

Interruption safety: every finished symbol is checkpointed; rerunning after
a crash resumes where it stopped.
"""

from __future__ import annotations

import logging
from datetime import datetime

from scraper.config.indices import IndexDefinition, get_index_registry
from scraper.config.settings import Settings
from scraper.db.connection import Database
from scraper.db.repository import CompanyRepository, RunRepository
from scraper.exporters.csv_exporter import CsvExporter
from scraper.exporters.excel_exporter import ExcelExporter
from scraper.models.company import (
    CompanyProfile,
    IndexConstituent,
    RunStats,
    ScrapeError,
)
from scraper.parsing.company_page import parse_company_page
from scraper.parsing.financials import (
    parse_period_results,
    parse_pricefeed,
    pricefeed_bse_symbol,
    pricefeed_company_name,
    pricefeed_industry,
    pricefeed_isin,
    pricefeed_sector,
)
from scraper.parsing.text_extract import extract_business_facets
from scraper.scraping.http_client import HttpClient, HttpError
from scraper.scraping.moneycontrol import McIdentity, MoneycontrolScraper
from scraper.scraping.nse_indices import NseIndexScraper
from scraper.utils.checkpoint import Checkpoint

logger = logging.getLogger(__name__)

# Static profile fields worth flagging in the "missing fields" report.
_REPORTED_FIELDS = (
    "business_summary", "website", "products_services", "major_clients",
    "order_book", "bse_symbol",
)


class ScraperPipeline:
    """Wires scraping, parsing, persistence and export together for one run."""

    def __init__(self, settings: Settings, database: Database) -> None:
        self._settings = settings
        self._db = database
        self._client = HttpClient(
            delay_seconds=settings.request_delay_seconds,
            jitter_seconds=settings.request_jitter_seconds,
            timeout_seconds=settings.request_timeout_seconds,
            max_retries=settings.max_retries,
            backoff_base=settings.retry_backoff_base,
        )
        self._companies = CompanyRepository(database)
        self._runs = RunRepository(database)
        self._nse = NseIndexScraper(self._client)
        self._mc = MoneycontrolScraper(self._client)
        self._checkpoint = Checkpoint(settings.checkpoint_path)
        self.stats = RunStats()

    # -- step 1+2: discovery and filtering ------------------------------------------

    def discover_it_companies(
        self,
        only_symbols: list[str] | None = None,
        limit: int | None = None,
    ) -> list[IndexConstituent]:
        """Fetch all configured indices and return the IT constituents."""
        indices = get_index_registry(self._settings.indices or None)
        index_by_key = {ix.key: ix for ix in indices}
        merged = self._nse.fetch_all(indices)
        self.stats.indices_fetched = len(indices)
        self.stats.constituents_seen = len(merged)

        it_companies = [
            c for c in merged.values()
            if self._is_it(c, index_by_key)
        ]
        it_companies.sort(key=lambda c: c.nse_symbol)
        if only_symbols:
            wanted = {s.upper() for s in only_symbols}
            it_companies = [c for c in it_companies if c.nse_symbol in wanted]
        if limit is not None:
            it_companies = it_companies[:limit]
        self.stats.it_companies = len(it_companies)
        logger.info(
            "Identified %d IT companies out of %d constituents",
            len(it_companies), len(merged),
        )
        return it_companies

    def _is_it(
        self, constituent: IndexConstituent,
        index_by_key: dict[str, IndexDefinition],
    ) -> bool:
        """IT when in an all-IT index or the NSE industry says so."""
        if any(
            index_by_key[key].all_constituents_are_it
            for key in constituent.index_keys
            if key in index_by_key
        ):
            return True
        return self._settings.is_it_industry(constituent.nse_industry)

    # -- step 3: per-company scraping -----------------------------------------------

    def scrape_company(
        self, constituent: IndexConstituent,
        index_by_key: dict[str, IndexDefinition],
    ) -> bool:
        """Scrape one company; returns True on success (data persisted)."""
        symbol = constituent.nse_symbol

        identity = self._resolve_identity(constituent)
        if identity is None:
            return False

        # Dynamic data -- refreshed on every run.
        pricefeed = self._fetch_pricefeed(symbol, identity)
        if pricefeed is None:
            return False
        self._fetch_period_results(symbol, identity)

        # Static data -- only when missing or stale.
        static_is_stale = self._static_is_stale(symbol)
        page_data = None
        if static_is_stale:
            page_data = self._fetch_static_page(symbol, identity)
            self.stats.static_refreshed += 1
        else:
            self.stats.static_cache_hits += 1
            logger.debug("%s: static cache fresh, skipping profile page", symbol)

        profile = self._build_profile(constituent, identity, pricefeed, page_data)
        self._companies.upsert_profile(profile)
        self._companies.set_index_membership(
            symbol,
            [
                (key, index_by_key[key].name)
                for key in constituent.index_keys
                if key in index_by_key
            ],
        )
        self._companies.upsert_market_data(parse_pricefeed(pricefeed, symbol))
        if page_data is not None and page_data.shareholding:
            self._companies.replace_shareholding(symbol, page_data.shareholding)
        self._companies.touch_dynamic(symbol)

        self._record_missing_fields(symbol, profile)
        return True

    def _resolve_identity(
        self, constituent: IndexConstituent
    ) -> McIdentity | None:
        symbol = constituent.nse_symbol
        try:
            identity = self._mc.resolve(symbol, constituent.isin or None)
        except (HttpError, ValueError) as exc:
            self._record_error(constituent, "resolve", str(exc))
            return None
        if identity is None:
            self._record_error(
                constituent, "resolve", "No Moneycontrol match for symbol/ISIN"
            )
        return identity

    def _fetch_pricefeed(
        self, symbol: str, identity: McIdentity
    ) -> dict | None:
        try:
            data = self._mc.fetch_pricefeed(identity.sc_id)
        except (HttpError, ValueError) as exc:
            self._record_error_symbol(symbol, "pricefeed", str(exc))
            return None
        if not data:
            self._record_error_symbol(symbol, "pricefeed", "Empty price feed")
            return None
        return data

    def _fetch_period_results(self, symbol: str, identity: McIdentity) -> None:
        for kind, period_type in (("quarterly", "Q"), ("yearly", "Y")):
            try:
                rows = self._mc.fetch_results(identity.sc_id, kind)
                results = parse_period_results(rows, symbol, period_type)
                self._companies.upsert_period_results(results)
                if not results:
                    self._record_missing(symbol, f"{kind}_results")
            except (HttpError, ValueError) as exc:
                # Missing financials are non-fatal: record and continue.
                self._record_error_symbol(symbol, kind, str(exc))

    def _fetch_static_page(self, symbol: str, identity: McIdentity):
        try:
            html = self._mc.fetch_company_page(identity.company_page_url)
            return parse_company_page(html, symbol)
        except (HttpError, ValueError) as exc:
            self._record_error_symbol(symbol, "profile", str(exc))
            return None

    def _static_is_stale(self, symbol: str) -> bool:
        age = self._companies.static_age_days(symbol)
        return age is None or age >= self._settings.static_refresh_days

    def _build_profile(
        self,
        constituent: IndexConstituent,
        identity: McIdentity,
        pricefeed: dict,
        page_data,
    ) -> CompanyProfile:
        """Merge NSE, price-feed and company-page data into one profile."""
        profile = CompanyProfile(
            nse_symbol=constituent.nse_symbol,
            company_name=identity.mc_name or constituent.company_name,
            isin=pricefeed_isin(pricefeed) or constituent.isin or None,
            bse_symbol=pricefeed_bse_symbol(pricefeed),
            mc_sc_id=identity.sc_id,
            mc_url=identity.company_page_url,
            sector=pricefeed_sector(pricefeed) or identity.mc_sector,
            industry=pricefeed_industry(pricefeed)
            or constituent.nse_industry or None,
        )
        if pricefeed_company_name(pricefeed):
            profile.company_name = pricefeed_company_name(pricefeed)
        if page_data is not None:
            profile.business_summary = page_data.business_summary
            profile.website = page_data.website
            profile.email = page_data.email
            profile.address = page_data.address
            profile.phone = page_data.phone
            profile.registrar = page_data.registrar
            profile.management = page_data.management
            profile.bse_symbol = page_data.bse_symbol or profile.bse_symbol
            profile.isin = page_data.isin or profile.isin
            facets = extract_business_facets(page_data.business_summary)
            profile.products_services = facets.products_services
            profile.major_clients = facets.major_clients
            profile.order_book = facets.order_book
        return profile

    # -- error / missing-field bookkeeping ----------------------------------------------

    def _record_error(
        self, constituent: IndexConstituent, stage: str, message: str
    ) -> None:
        logger.error("%s [%s]: %s", constituent.nse_symbol, stage, message)
        self.stats.errors.append(
            ScrapeError(
                nse_symbol=constituent.nse_symbol,
                company_name=constituent.company_name,
                stage=stage,
                message=message,
            )
        )

    def _record_error_symbol(self, symbol: str, stage: str, message: str) -> None:
        logger.error("%s [%s]: %s", symbol, stage, message)
        self.stats.errors.append(
            ScrapeError(nse_symbol=symbol, company_name=None, stage=stage,
                        message=message)
        )

    def _record_missing(self, symbol: str, field_name: str) -> None:
        self.stats.missing_fields.setdefault(symbol, [])
        if field_name not in self.stats.missing_fields[symbol]:
            self.stats.missing_fields[symbol].append(field_name)

    def _record_missing_fields(self, symbol: str, profile: CompanyProfile) -> None:
        for field_name in _REPORTED_FIELDS:
            if getattr(profile, field_name) is None:
                self._record_missing(symbol, field_name)

    # -- step 4: full run --------------------------------------------------------------

    def run(
        self,
        only_symbols: list[str] | None = None,
        limit: int | None = None,
        fresh: bool = False,
        export: bool = True,
    ) -> RunStats:
        """Execute a complete scrape-and-export run."""
        self._db.create_schema()
        run_id = self._runs.start_run(self.stats)
        if fresh:
            self._checkpoint.clear()
        else:
            self._checkpoint.load()

        interrupted = False
        scraped_symbols: list[str] = []
        try:
            indices = get_index_registry(self._settings.indices or None)
            index_by_key = {ix.key: ix for ix in indices}
            companies = self.discover_it_companies(only_symbols, limit)

            for position, constituent in enumerate(companies, start=1):
                symbol = constituent.nse_symbol
                if self._checkpoint.is_done(symbol):
                    logger.info("[%d/%d] %s: checkpointed, skipping",
                                position, len(companies), symbol)
                    scraped_symbols.append(symbol)
                    continue
                logger.info("[%d/%d] Scraping %s (%s)", position,
                            len(companies), symbol, constituent.company_name)
                try:
                    success = self.scrape_company(constituent, index_by_key)
                except Exception as exc:  # noqa: BLE001 - keep the run alive
                    logger.exception("%s: unexpected failure", symbol)
                    self._record_error(constituent, "unexpected", repr(exc))
                    success = False
                if success:
                    scraped_symbols.append(symbol)
                    self.stats.companies_scraped += 1
                    self._checkpoint.mark_done(symbol)
                else:
                    self.stats.companies_failed += 1
        except KeyboardInterrupt:
            interrupted = True
            logger.warning("Interrupted -- progress checkpointed, rerun to resume")
        finally:
            self.stats.requests_made = self._client.requests_made
            self.stats.finished_at = datetime.now()

            if export and scraped_symbols:
                self._export(scraped_symbols)

            notes = "interrupted" if interrupted else "completed"
            self._runs.finish_run(run_id, self.stats, notes=notes)
            if not interrupted:
                self._checkpoint.clear()
            self._log_summary()
        return self.stats

    def _export(self, symbols: list[str]) -> None:
        companies = self._companies.fetch_companies_for_export(symbols)
        membership = self._companies.fetch_index_membership(symbols)
        quarterly = self._companies.fetch_period_results(
            symbols, "Q", limit_per_company=3
        )
        annual = self._companies.fetch_period_results(symbols, "Y")
        shareholding = self._companies.fetch_shareholding(symbols)

        if self._settings.export_excel:
            ExcelExporter(self._settings.export_dir).export(
                companies, membership, quarterly, annual, shareholding, self.stats
            )
        if self._settings.export_csv:
            CsvExporter(self._settings.export_dir).export(
                companies, quarterly, annual, shareholding
            )

    def _log_summary(self) -> None:
        s = self.stats
        logger.info(
            "Run finished in %.1fs | indices=%d constituents=%d it=%d "
            "scraped=%d failed=%d static_refreshed=%d cache_hits=%d requests=%d "
            "errors=%d",
            s.duration_seconds, s.indices_fetched, s.constituents_seen,
            s.it_companies, s.companies_scraped, s.companies_failed,
            s.static_refreshed, s.static_cache_hits, s.requests_made,
            len(s.errors),
        )

"""Dataclasses describing everything the scraper collects.

Two families of data exist:

* **Static** (:class:`CompanyProfile`) -- changes rarely; cached in the DB and
  refreshed only when missing or older than ``STATIC_REFRESH_DAYS``.
* **Dynamic** (:class:`MarketData`, :class:`PeriodResult`,
  :class:`ShareholdingEntry`) -- refreshed on every run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class IndexConstituent:
    """One row of an NSE index constituents CSV."""

    company_name: str
    nse_symbol: str
    nse_industry: str
    isin: str
    index_keys: list[str] = field(default_factory=list)


@dataclass
class CompanyProfile:
    """Static (slow-changing) company information."""

    nse_symbol: str
    company_name: str | None = None
    bse_symbol: str | None = None
    isin: str | None = None
    mc_sc_id: str | None = None            # Moneycontrol internal id
    mc_url: str | None = None
    sector: str | None = None
    industry: str | None = None
    business_summary: str | None = None
    products_services: str | None = None   # best-effort extraction
    major_clients: str | None = None       # best-effort extraction
    order_book: str | None = None          # best-effort extraction
    website: str | None = None
    email: str | None = None
    address: str | None = None
    phone: str | None = None
    registrar: str | None = None
    management: str | None = None          # "Name (Designation); ..." string
    listed_indices: str | None = None      # comma-joined NSE index names


@dataclass
class MarketData:
    """Dynamic market snapshot (from the Moneycontrol price feed)."""

    nse_symbol: str
    market_cap_cr: float | None = None     # Rs. crore
    price: float | None = None
    pe: float | None = None
    pb: float | None = None
    industry_pe: float | None = None
    dividend_yield: float | None = None
    book_value: float | None = None
    eps_ttm: float | None = None
    face_value: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None
    shares_outstanding: float | None = None


@dataclass
class PeriodResult:
    """One reporting period (a quarter or a fiscal year) of P&L figures.

    All money figures are Rs. crore, as published by Moneycontrol.
    ``period_type`` is ``"Q"`` for quarterly and ``"Y"`` for annual rows.
    """

    nse_symbol: str
    period_type: str                       # "Q" | "Y"
    period_label: str                      # e.g. "Mar '26"
    revenue: float | None = None           # Net sales / income from operations
    other_income: float | None = None
    total_income: float | None = None
    expenditure: float | None = None
    interest: float | None = None
    tax: float | None = None
    net_profit: float | None = None
    basic_eps: float | None = None


@dataclass
class ShareholdingEntry:
    """One holder category of the shareholding pattern (percent of equity)."""

    nse_symbol: str
    category: str                          # Promoter / FII / DII / Public / Others
    percent: float


@dataclass
class ScrapeError:
    """A failure captured during a run (also exported to Excel)."""

    nse_symbol: str
    company_name: str | None
    stage: str                             # e.g. "resolve", "profile", "quarterly"
    message: str
    occurred_at: datetime = field(default_factory=datetime.now)


@dataclass
class RunStats:
    """Aggregate statistics for one scraper execution."""

    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    indices_fetched: int = 0
    constituents_seen: int = 0
    it_companies: int = 0
    companies_scraped: int = 0
    static_refreshed: int = 0
    static_cache_hits: int = 0
    companies_failed: int = 0
    requests_made: int = 0
    errors: list[ScrapeError] = field(default_factory=list)
    missing_fields: dict[str, list[str]] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        end = self.finished_at or datetime.now()
        return (end - self.started_at).total_seconds()

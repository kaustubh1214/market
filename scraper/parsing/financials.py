"""Parsers for Moneycontrol JSON feeds (price feed + results feed)."""

from __future__ import annotations

import logging

from scraper.models.company import MarketData, PeriodResult
from scraper.utils.helpers import clean_text, parse_number

logger = logging.getLogger(__name__)

# Results-feed rows use these keys (values are strings like "58,052.00" / "--").
_REVENUE_KEYS = (
    "Net Sales/Income from operations",
    "Total Income From Operations",
)
_NET_PROFIT_KEYS = (
    "Net Profit/(Loss) For the Period",
    "P/L After Tax from Ordinary Activities",
)


def parse_pricefeed(data: dict, nse_symbol: str) -> MarketData:
    """Map the price-feed JSON to a :class:`MarketData` snapshot."""
    return MarketData(
        nse_symbol=nse_symbol,
        market_cap_cr=parse_number(data.get("MKTCAP")),
        price=parse_number(data.get("pricecurrent")),
        pe=parse_number(data.get("PE")),
        pb=parse_number(data.get("PB")),
        industry_pe=parse_number(data.get("IND_PE")),
        dividend_yield=parse_number(data.get("DY")),
        book_value=parse_number(data.get("BV")),
        eps_ttm=parse_number(data.get("SC_TTM")),
        face_value=parse_number(data.get("FV")),
        week52_high=parse_number(data.get("52H")),
        week52_low=parse_number(data.get("52L")),
        shares_outstanding=parse_number(data.get("SHRS")),
    )


def pricefeed_sector(data: dict) -> str | None:
    """Sector name as reported by Moneycontrol ("Software & IT Services")."""
    return clean_text(data.get("main_sector"))


def pricefeed_industry(data: dict) -> str | None:
    """Industry / sub-sector ("IT Services & Consulting")."""
    return clean_text(data.get("newSubsector")) or clean_text(data.get("SC_SUBSEC"))


def pricefeed_company_name(data: dict) -> str | None:
    return clean_text(data.get("SC_FULLNM")) or clean_text(data.get("company"))


def pricefeed_bse_symbol(data: dict) -> str | None:
    return clean_text(data.get("BSEID"))


def pricefeed_isin(data: dict) -> str | None:
    return clean_text(data.get("isinid"))


def _first_number(row: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = parse_number(row.get(key))
        if value is not None:
            return value
    return None


def parse_period_results(
    rows: list[dict], nse_symbol: str, period_type: str
) -> list[PeriodResult]:
    """Map results-feed rows to :class:`PeriodResult` (newest row first).

    Rows without a period label (``yrc0``) are ignored; rows where every
    numeric field is missing are dropped as well.
    """
    results: list[PeriodResult] = []
    for row in rows:
        label = clean_text(row.get("yrc0"))
        if not label:
            continue
        result = PeriodResult(
            nse_symbol=nse_symbol,
            period_type=period_type,
            period_label=label,
            revenue=_first_number(row, _REVENUE_KEYS),
            other_income=parse_number(row.get("Other Income")),
            total_income=_first_number(
                row, ("Total Income From Operations", "Total Income")
            ),
            expenditure=parse_number(row.get("Total Expenditure")),
            interest=parse_number(row.get("Interest")),
            tax=parse_number(row.get("Tax")),
            net_profit=_first_number(row, _NET_PROFIT_KEYS),
            basic_eps=parse_number(row.get("Basic EPS")),
        )
        has_data = any(
            getattr(result, name) is not None
            for name in ("revenue", "net_profit", "total_income", "basic_eps")
        )
        if has_data:
            results.append(result)
    return results

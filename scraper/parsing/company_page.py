"""Parser for the classic Moneycontrol company page.

The page carries three machine-readable payloads:

1. ``#company_info div.morepls_cnt`` -- the "About the Company" text.
2. A hidden ``<div>`` containing a JSON blob with address, website,
   management, registrar and exchange identifiers.
3. An inline script with ``var summary_jsn = '{"Promoter":71.77,...}'`` --
   the shareholding-pattern summary.

Each extraction is independent and failure-tolerant: a redesign of one block
must not break the others.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from scraper.models.company import ShareholdingEntry
from scraper.utils.helpers import clean_text

logger = logging.getLogger(__name__)

_COMPANY_INFO_JSON_RE = re.compile(
    r'<div[^>]*style="display:\s*none;?"[^>]*>\s*(\{&quot;success&quot;.*?\})\s*</div>',
    re.DOTALL,
)
_SHAREHOLDING_RE = re.compile(r"var\s+summary_jsn\s*=\s*'(\{.*?\})'", re.DOTALL)


@dataclass
class CompanyPageData:
    """Everything extractable from one company page."""

    business_summary: str | None = None
    website: str | None = None
    email: str | None = None
    address: str | None = None
    phone: str | None = None
    registrar: str | None = None
    management: str | None = None
    bse_symbol: str | None = None
    isin: str | None = None
    shareholding: list[ShareholdingEntry] = field(default_factory=list)


_PLACEHOLDER_SUMMARIES = {"data is not available", "data not available"}


def _parse_business_summary(soup: BeautifulSoup) -> str | None:
    container = soup.select_one("#company_info .morepls_cnt")
    if container is None:
        container = soup.select_one("#company_info .com_overviewcnt")
    if container is None:
        return None
    text = clean_text(container.get_text(" ", strip=True))
    # Moneycontrol renders a literal placeholder when it has no profile text.
    if text and text.strip(". ").lower() in _PLACEHOLDER_SUMMARIES:
        return None
    return text


def _parse_info_blob(html: str) -> dict:
    """Decode the hidden company-info JSON (HTML-entity escaped)."""
    match = _COMPANY_INFO_JSON_RE.search(html)
    if not match:
        return {}
    raw = (
        match.group(1)
        .replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&#039;", "'")
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.debug("Company-info JSON blob unparsable: %s", exc)
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _parse_shareholding(html: str, nse_symbol: str) -> list[ShareholdingEntry]:
    match = _SHAREHOLDING_RE.search(html)
    if not match:
        return []
    try:
        summary = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    entries: list[ShareholdingEntry] = []
    for category, percent in summary.items():
        if isinstance(percent, (int, float)):
            entries.append(
                ShareholdingEntry(
                    nse_symbol=nse_symbol,
                    category=str(category),
                    percent=float(percent),
                )
            )
    return entries


def parse_company_page(html: str, nse_symbol: str) -> CompanyPageData:
    """Extract all static payloads from a company page.

    Never raises on missing sections; absent data stays ``None`` so the
    pipeline can record it as a missing field rather than a failure.
    """
    soup = BeautifulSoup(html, "lxml")
    result = CompanyPageData()
    result.business_summary = _parse_business_summary(soup)
    result.shareholding = _parse_shareholding(html, nse_symbol)

    info = _parse_info_blob(html)
    if info:
        address = info.get("address") or {}
        if isinstance(address, dict):
            parts = [
                clean_text(address.get(key))
                for key in ("address1", "address2", "city", "state", "pincode")
            ]
            joined = ", ".join(p for p in parts if p)
            result.address = joined or None
            result.website = clean_text(address.get("web"))
            result.email = clean_text(address.get("email"))
            result.phone = clean_text(address.get("telephone1"))

        management = info.get("management") or []
        if isinstance(management, list):
            people = [
                f"{clean_text(m.get('name'))} ({clean_text(m.get('designation'))})"
                for m in management
                if isinstance(m, dict) and clean_text(m.get("name"))
            ]
            result.management = "; ".join(people) or None

        registrars = info.get("registrars") or {}
        if isinstance(registrars, dict):
            result.registrar = clean_text(registrars.get("name"))

        details = info.get("details") or {}
        if isinstance(details, dict):
            result.bse_symbol = clean_text(details.get("bseId"))
            result.isin = clean_text(details.get("isinid"))

    return result

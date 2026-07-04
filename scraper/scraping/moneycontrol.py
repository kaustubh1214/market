"""Moneycontrol fetchers: raw bytes/JSON in, no HTML parsing here.

Endpoints used (all verified against the live site):

* **Autosuggest** -- resolves an NSE symbol to Moneycontrol's internal
  ``sc_id`` and the company page URL. Results can contain unrelated
  companies, so callers must match candidates by ISIN / NSE symbol.
* **Price feed** -- ``priceapi.moneycontrol.com/pricefeed/nse/equitycash/{scId}``
  JSON with market cap, ratios, sector, ISIN, BSE/NSE ids.
* **Company page** -- classic HTML page carrying the "About the Company"
  text, a hidden company-info JSON blob and the shareholding summary.
* **Results feed** -- ``appfeeds.moneycontrol.com/jsonapi/stocks/
  {quarterly|yearly}_results_responsive`` JSON with per-period P&L tables.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib.parse import quote

from scraper.scraping.http_client import HttpClient
from scraper.utils.helpers import clean_text

logger = logging.getLogger(__name__)

AUTOSUGGEST_URL = (
    "https://www.moneycontrol.com/mccode/common/autosuggestion_solr.php"
    "?classic=true&query={query}&type=1&format=json"
)
PRICEFEED_URL = "https://priceapi.moneycontrol.com/pricefeed/nse/equitycash/{sc_id}"
RESULTS_URL = (
    "https://appfeeds.moneycontrol.com/jsonapi/stocks/{kind}_results_responsive"
    "?sc_id={sc_id}&type_format={kind}&start=0&limit={limit}"
)


@dataclass(frozen=True)
class McIdentity:
    """Resolution of an NSE symbol to Moneycontrol identifiers."""

    sc_id: str
    company_page_url: str
    mc_name: str
    mc_sector: str | None


class MoneycontrolScraper:
    """All raw Moneycontrol fetch operations."""

    def __init__(self, client: HttpClient) -> None:
        self._client = client

    # -- identity resolution ------------------------------------------------------

    def resolve(self, nse_symbol: str, isin: str | None) -> McIdentity | None:
        """Map an NSE symbol to Moneycontrol ids via the autosuggest API.

        The suggest API is fuzzy (querying "COFORGE" returns Bharat Forge
        first), so candidates are matched primarily by ISIN and secondarily
        by the exact NSE symbol embedded in the display name.
        """
        url = AUTOSUGGEST_URL.format(query=quote(nse_symbol))
        payload = json.loads(self._client.get_text(url))
        if not isinstance(payload, list):
            return None

        def to_identity(entry: dict) -> McIdentity | None:
            sc_id = clean_text(entry.get("sc_id"))
            link = clean_text(entry.get("link_src"))
            if not sc_id or not link:
                return None
            return McIdentity(
                sc_id=sc_id,
                company_page_url=link,
                mc_name=clean_text(entry.get("name")) or nse_symbol,
                mc_sector=clean_text(entry.get("sc_sector")),
            )

        fallback: McIdentity | None = None
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            display = str(entry.get("pdt_dis_nm", ""))
            # display format: "Name&nbsp;<span>ISIN, NSESYMBOL, BSECODE</span>"
            if isin and isin in display:
                return to_identity(entry)
            tokens = [t.strip() for t in
                      display.replace("<span>", ",").replace("</span>", ",").split(",")]
            if nse_symbol in tokens:
                fallback = fallback or to_identity(entry)
        if fallback:
            return fallback
        logger.warning("%s: no Moneycontrol match (isin=%s)", nse_symbol, isin)
        return None

    # -- dynamic feeds ----------------------------------------------------------------

    def fetch_pricefeed(self, sc_id: str) -> dict:
        """Market snapshot JSON; returns the ``data`` object (may be empty)."""
        raw = self._client.get_text(PRICEFEED_URL.format(sc_id=quote(sc_id)))
        payload = json.loads(raw)
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def fetch_results(self, sc_id: str, kind: str, limit: int = 8) -> list[dict]:
        """Per-period P&L rows. ``kind`` is ``"quarterly"`` or ``"yearly"``."""
        if kind not in ("quarterly", "yearly"):
            raise ValueError(f"Unsupported results kind: {kind}")
        url = RESULTS_URL.format(kind=kind, sc_id=quote(sc_id), limit=limit)
        payload = json.loads(self._client.get_text(url))
        data = payload.get("data")
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        return []

    # -- static page --------------------------------------------------------------------

    def fetch_company_page(self, company_page_url: str) -> str:
        """The classic company profile page HTML (static data source)."""
        return self._client.get_text(company_page_url)

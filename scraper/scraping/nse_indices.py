"""Fetch NSE index constituents from the NSE archives CSVs.

Each CSV has the columns::

    Company Name, Industry, Symbol, Series, ISIN Code

The ``Industry`` column drives the primary IT-sector filter.
"""

from __future__ import annotations

import csv
import io
import logging

from scraper.config.indices import IndexDefinition
from scraper.models.company import IndexConstituent
from scraper.scraping.http_client import HttpClient
from scraper.utils.helpers import clean_text

logger = logging.getLogger(__name__)


class NseIndexScraper:
    """Downloads and merges constituents of the configured NSE indices."""

    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def fetch_index(self, index: IndexDefinition) -> list[IndexConstituent]:
        """Download one index CSV and parse its rows."""
        logger.info("Fetching index constituents: %s", index.name)
        text = self._client.get_text(index.csv_url)
        reader = csv.DictReader(io.StringIO(text))
        constituents: list[IndexConstituent] = []
        for row in reader:
            symbol = clean_text(row.get("Symbol"))
            name = clean_text(row.get("Company Name"))
            if not symbol or not name:
                continue
            constituents.append(
                IndexConstituent(
                    company_name=name,
                    nse_symbol=symbol,
                    nse_industry=clean_text(row.get("Industry")) or "",
                    isin=clean_text(row.get("ISIN Code")) or "",
                    index_keys=[index.key],
                )
            )
        logger.info("%s: %d constituents", index.name, len(constituents))
        return constituents

    def fetch_all(
        self, indices: list[IndexDefinition]
    ) -> dict[str, IndexConstituent]:
        """Fetch every index and merge by symbol (union of index memberships)."""
        merged: dict[str, IndexConstituent] = {}
        for index in indices:
            for constituent in self.fetch_index(index):
                known = merged.get(constituent.nse_symbol)
                if known is None:
                    merged[constituent.nse_symbol] = constituent
                elif index.key not in known.index_keys:
                    known.index_keys.append(index.key)
        return merged

"""Scraping layer: HTTP client and site-specific fetchers (no parsing here)."""

from scraper.scraping.http_client import HttpClient, HttpError
from scraper.scraping.nse_indices import NseIndexScraper
from scraper.scraping.moneycontrol import MoneycontrolScraper

__all__ = ["HttpClient", "HttpError", "NseIndexScraper", "MoneycontrolScraper"]

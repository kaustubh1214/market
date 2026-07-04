"""Tests for configuration: settings helpers and the index registry."""

import pytest

from scraper.config.indices import DEFAULT_INDICES, get_index_registry
from scraper.config.settings import Settings


class TestIndexRegistry:
    def test_default_contains_required_indices(self):
        keys = {ix.key for ix in DEFAULT_INDICES}
        assert {
            "nifty_it", "nifty_midcap_150", "nifty_midsmallcap_400",
            "nifty_smallcap_250", "nifty_largemidcap_250", "nifty_midcap_select",
        } <= keys

    def test_nifty_it_flagged_all_it(self):
        nifty_it = next(ix for ix in DEFAULT_INDICES if ix.key == "nifty_it")
        assert nifty_it.all_constituents_are_it

    def test_subset_selection(self):
        subset = get_index_registry(["nifty_it"])
        assert len(subset) == 1 and subset[0].key == "nifty_it"

    def test_unknown_key_fails_fast(self):
        with pytest.raises(KeyError):
            get_index_registry(["nifty_typo"])

    def test_csv_urls_wellformed(self):
        for ix in DEFAULT_INDICES:
            assert ix.csv_url.startswith(
                "https://archives.nseindia.com/content/indices/ind_"
            )


class TestSectorMatching:
    def test_nse_industry_match_case_insensitive(self):
        settings = Settings()
        assert settings.is_it_industry("Information Technology")
        assert settings.is_it_industry("  information technology ")
        assert not settings.is_it_industry("Financial Services")
        assert not settings.is_it_industry(None)

    def test_mc_sector_match(self):
        settings = Settings()
        assert settings.is_it_mc_sector("Software & IT Services")
        assert not settings.is_it_mc_sector("Metals & Mining")

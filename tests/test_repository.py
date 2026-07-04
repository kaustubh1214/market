"""Tests for the repository layer against a temporary SQLite database."""

import pytest

from scraper.db.connection import Database
from scraper.db.repository import CompanyRepository
from scraper.models.company import (
    CompanyProfile,
    MarketData,
    PeriodResult,
    ShareholdingEntry,
)


@pytest.fixture()
def repo(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_schema()
    yield CompanyRepository(db)
    db.close()


class TestUpsertProfile:
    def test_insert_then_no_change(self, repo):
        profile = CompanyProfile(
            nse_symbol="TCS", company_name="Tata Consultancy Services",
            sector="Software & IT Services", website="https://www.tcs.com",
        )
        first = repo.upsert_profile(profile)
        assert "company_name" in first and "website" in first
        second = repo.upsert_profile(profile)
        assert second == []  # identical rerun writes nothing

    def test_update_only_changed_field(self, repo):
        repo.upsert_profile(CompanyProfile(nse_symbol="TCS", company_name="Old"))
        changed = repo.upsert_profile(
            CompanyProfile(nse_symbol="TCS", company_name="New")
        )
        assert changed == ["company_name"]

    def test_none_does_not_erase(self, repo):
        repo.upsert_profile(
            CompanyProfile(nse_symbol="TCS", website="https://www.tcs.com")
        )
        repo.upsert_profile(CompanyProfile(nse_symbol="TCS", website=None))
        row = repo.fetch_companies_for_export(["TCS"])[0]
        assert row["website"] == "https://www.tcs.com"

    def test_no_duplicate_companies(self, repo):
        id_a = repo.ensure_company("TCS")
        id_b = repo.ensure_company("TCS")
        assert id_a == id_b


class TestStaticAge:
    def test_unknown_company(self, repo):
        assert repo.static_age_days("NOPE") is None

    def test_stub_without_summary_counts_as_never(self, repo):
        repo.upsert_profile(CompanyProfile(nse_symbol="TCS", company_name="X"))
        assert repo.static_age_days("TCS") is None

    def test_fresh_profile_has_small_age(self, repo):
        repo.upsert_profile(
            CompanyProfile(nse_symbol="TCS", business_summary="An IT company.")
        )
        age = repo.static_age_days("TCS")
        assert age is not None and age < 0.01


class TestMarketData:
    def test_insert_and_idempotent_update(self, repo):
        data = MarketData(nse_symbol="TCS", market_cap_cr=750000.0, pe=15.4)
        assert repo.upsert_market_data(data) != []
        assert repo.upsert_market_data(data) == []
        data.pe = 16.0
        assert repo.upsert_market_data(data) == ["pe"]


class TestPeriodResults:
    def test_upsert_and_limit(self, repo):
        rows = [
            PeriodResult(nse_symbol="TCS", period_type="Q",
                         period_label=label, revenue=float(i), net_profit=1.0)
            for i, label in enumerate(
                ["Mar '26", "Dec '25", "Sep '25", "Jun '25"]
            )
        ]
        assert repo.upsert_period_results(rows) == 4
        assert repo.upsert_period_results(rows) == 0  # unchanged rerun
        limited = repo.fetch_period_results(["TCS"], "Q", limit_per_company=3)
        labels = [r["period_label"] for r in limited]
        assert labels == ["Mar '26", "Dec '25", "Sep '25"]  # newest 3 first

    def test_later_run_insertion_keeps_label_order(self, repo):
        """A quarter added by a later run must sort by label, not rowid."""
        older = [
            PeriodResult(nse_symbol="TCS", period_type="Q",
                         period_label=label, revenue=1.0)
            for label in ["Mar '26", "Dec '25", "Sep '25"]
        ]
        repo.upsert_period_results(older)
        repo.upsert_period_results(
            [PeriodResult(nse_symbol="TCS", period_type="Q",
                          period_label="Jun '26", revenue=2.0)]
        )
        labels = [
            r["period_label"]
            for r in repo.fetch_period_results(["TCS"], "Q", limit_per_company=3)
        ]
        assert labels == ["Jun '26", "Mar '26", "Dec '25"]


class TestShareholding:
    def test_replace(self, repo):
        entries = [
            ShareholdingEntry(nse_symbol="TCS", category="Promoter", percent=71.8),
            ShareholdingEntry(nse_symbol="TCS", category="FII", percent=9.7),
        ]
        repo.replace_shareholding("TCS", entries)
        repo.replace_shareholding(
            "TCS",
            [ShareholdingEntry(nse_symbol="TCS", category="Promoter", percent=70.0)],
        )
        rows = repo.fetch_shareholding(["TCS"])
        assert len(rows) == 1 and rows[0]["percent"] == 70.0

    def test_empty_list_keeps_existing(self, repo):
        repo.replace_shareholding(
            "TCS",
            [ShareholdingEntry(nse_symbol="TCS", category="Promoter", percent=70.0)],
        )
        repo.replace_shareholding("TCS", [])
        assert len(repo.fetch_shareholding(["TCS"])) == 1


class TestIndexMembership:
    def test_membership_roundtrip(self, repo):
        repo.set_index_membership(
            "TCS", [("nifty_it", "Nifty IT"), ("nifty_50", "Nifty 50")]
        )
        membership = repo.fetch_index_membership(["TCS"])
        assert membership["TCS"] == ["Nifty 50", "Nifty IT"]

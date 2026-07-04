"""Tests for scraper.utils.helpers."""

from scraper.utils.helpers import (
    clean_text,
    parse_db_timestamp,
    parse_number,
    period_sort_key,
)


class TestParseNumber:
    def test_plain_float(self):
        assert parse_number(757446.62) == 757446.62

    def test_indian_thousands(self):
        assert parse_number("70,698.00") == 70698.0

    def test_placeholder_dashes(self):
        assert parse_number("--") is None
        assert parse_number("-") is None

    def test_none_and_empty(self):
        assert parse_number(None) is None
        assert parse_number("") is None

    def test_garbage(self):
        assert parse_number("N.A.") is None
        assert parse_number("abc") is None

    def test_percent_and_currency_noise(self):
        assert parse_number("5.25%") == 5.25
        assert parse_number("Rs. 1,234.50 Cr") == 1234.5


class TestCleanText:
    def test_collapses_whitespace(self):
        assert clean_text("  a \n\t b  ") == "a b"

    def test_html_entities(self):
        assert clean_text("Tata&nbsp;Consultancy &amp; Co") == "Tata Consultancy & Co"

    def test_placeholders_become_none(self):
        for raw in ("", "-", "--", "N.A.", "null"):
            assert clean_text(raw) is None

    def test_none_passthrough(self):
        assert clean_text(None) is None


class TestPeriodSortKey:
    def test_quarter_labels(self):
        assert period_sort_key("Mar '26") == (2026, 3)
        assert period_sort_key("Dec '25") == (2025, 12)

    def test_full_year(self):
        assert period_sort_key("Mar 2024") == (2024, 3)

    def test_ordering(self):
        labels = ["Jun '25", "Mar '26", "Dec '25"]
        assert sorted(labels, key=period_sort_key) == [
            "Jun '25", "Dec '25", "Mar '26"
        ]

    def test_garbage_sorts_first(self):
        assert period_sort_key(None) == (0, 0)
        assert period_sort_key("???") == (0, 0)


class TestParseDbTimestamp:
    def test_roundtrip(self):
        parsed = parse_db_timestamp("2026-07-04 10:30:00")
        assert parsed is not None
        assert parsed.year == 2026 and parsed.tzinfo is not None

    def test_invalid(self):
        assert parse_db_timestamp("not-a-date") is None
        assert parse_db_timestamp(None) is None

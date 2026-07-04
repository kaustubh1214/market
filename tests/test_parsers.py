"""Tests for the parsing layer using representative page/feed snippets."""

from scraper.parsing.company_page import parse_company_page
from scraper.parsing.financials import (
    parse_period_results,
    parse_pricefeed,
    pricefeed_industry,
    pricefeed_sector,
)
from scraper.parsing.text_extract import extract_business_facets

COMPANY_PAGE_HTML = """
<html><body>
<div id="company_info">
  <div class="common_heading"><h2>About the Company</h2></div>
  <div class="com_overviewcnt">
    <div class="morepls_cnt">Acme Infotech is an IT solution provider. The
    company offers consulting and platform services. It serves clients in
    banking and retail. The order book stood at Rs 5,000 crore.</div>
  </div>
  <div style="display: none;">{&quot;success&quot;:1,&quot;data&quot;:{&quot;address&quot;:{&quot;address1&quot;:&quot;1 Tech Park&quot;,&quot;address2&quot;:&quot;&quot;,&quot;city&quot;:&quot;Pune&quot;,&quot;state&quot;:&quot;Maharashtra&quot;,&quot;pincode&quot;:&quot;411001&quot;,&quot;telephone1&quot;:&quot;020-123456&quot;,&quot;email&quot;:&quot;ir@acme.com&quot;,&quot;web&quot;:&quot;https:\\/\\/www.acme.com&quot;},&quot;management&quot;:[{&quot;name&quot;:&quot;A Kumar&quot;,&quot;designation&quot;:&quot;CEO&quot;}],&quot;registrars&quot;:{&quot;name&quot;:&quot;RegCo Ltd.&quot;},&quot;details&quot;:{&quot;bseId&quot;:&quot;500123&quot;,&quot;nseId&quot;:&quot;ACME&quot;,&quot;isinid&quot;:&quot;INE000A01001&quot;}}}</div>
</div>
<script>
    var summary_jsn = '{"Promoter":60.5,"FII":10.2,"DII":15.0,"Public":14.3,"Others":0.0}';
</script>
</body></html>
"""


class TestCompanyPageParser:
    def test_business_summary(self):
        data = parse_company_page(COMPANY_PAGE_HTML, "ACME")
        assert data.business_summary is not None
        assert data.business_summary.startswith("Acme Infotech")

    def test_info_blob(self):
        data = parse_company_page(COMPANY_PAGE_HTML, "ACME")
        assert data.website == "https://www.acme.com"
        assert data.email == "ir@acme.com"
        assert data.bse_symbol == "500123"
        assert data.isin == "INE000A01001"
        assert data.registrar == "RegCo Ltd."
        assert data.management == "A Kumar (CEO)"
        assert data.address is not None and "Pune" in data.address

    def test_shareholding(self):
        data = parse_company_page(COMPANY_PAGE_HTML, "ACME")
        categories = {e.category: e.percent for e in data.shareholding}
        assert categories["Promoter"] == 60.5
        assert categories["Others"] == 0.0

    def test_empty_page_never_raises(self):
        data = parse_company_page("<html><body></body></html>", "ACME")
        assert data.business_summary is None
        assert data.shareholding == []

    def test_placeholder_summary_becomes_none(self):
        html = (
            '<div id="company_info"><div class="morepls_cnt">'
            "Data is not Available</div></div>"
        )
        data = parse_company_page(html, "ACME")
        assert data.business_summary is None


class TestPricefeedParser:
    FEED = {
        "MKTCAP": 757446.62,
        "pricecurrent": "2093.50",
        "PE": 15.43,
        "PB": 8.95,
        "IND_PE": "22.1",
        "DY": 5.25,
        "BV": "234.03",
        "SC_TTM": "135.7",
        "FV": "1.00",
        "52H": "3427.00",
        "52L": "1976.80",
        "SHRS": "3618087518",
        "main_sector": "Software & IT Services",
        "newSubsector": "IT Services & Consulting",
    }

    def test_market_data(self):
        md = parse_pricefeed(self.FEED, "TCS")
        assert md.market_cap_cr == 757446.62
        assert md.price == 2093.5
        assert md.eps_ttm == 135.7
        assert md.week52_low == 1976.8

    def test_sector_helpers(self):
        assert pricefeed_sector(self.FEED) == "Software & IT Services"
        assert pricefeed_industry(self.FEED) == "IT Services & Consulting"

    def test_missing_fields_are_none(self):
        md = parse_pricefeed({}, "TCS")
        assert md.market_cap_cr is None
        assert md.pe is None


class TestPeriodResultsParser:
    ROWS = [
        {
            "yrc0": "Mar '26",
            "Net Sales/Income from operations": "58,052.00",
            "Other Income": "3,516.00",
            "Total Income From Operations": "58,052.00",
            "Interest": "238.00",
            "Tax": "3,938.00",
            "Net Profit/(Loss) For the Period": "14,526.00",
            "Basic EPS": "40.15",
        },
        {"yrc0": "Dec '25", "Net Sales/Income from operations": "--"},
        {"no_label": True},
    ]

    def test_parse(self):
        results = parse_period_results(self.ROWS, "TCS", "Q")
        assert len(results) == 1  # empty and label-less rows dropped
        first = results[0]
        assert first.period_label == "Mar '26"
        assert first.revenue == 58052.0
        assert first.net_profit == 14526.0
        assert first.basic_eps == 40.15
        assert first.period_type == "Q"


class TestBusinessFacets:
    SUMMARY = (
        "Acme Infotech is an IT solution provider. "
        "The company offers consulting and platform services. "
        "It serves clients in banking and retail. "
        "The order book stood at Rs 5,000 crore. "
        "It was founded in 1990."
    )

    def test_facets_extracted(self):
        facets = extract_business_facets(self.SUMMARY)
        assert "consulting and platform services" in facets.products_services
        assert "clients in banking" in facets.major_clients
        assert "order book" in facets.order_book.lower()

    def test_no_summary(self):
        facets = extract_business_facets(None)
        assert facets.products_services is None
        assert facets.major_clients is None
        assert facets.order_book is None

    def test_unrelated_text(self):
        facets = extract_business_facets("It was founded in 1990.")
        assert facets.order_book is None

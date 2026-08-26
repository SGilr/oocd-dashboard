"""Tests for asset discovery on the landing page.

The landing page markup is not under our control, so discovery is a pure
function over the page HTML and is tested against a saved shape of it. When the
Home Office changes the page, this test is where the change shows up.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from fetch import (  # noqa: E402
    KIND_FORCE_AREA_CRIME,
    KIND_OUTCOMES,
    KIND_USER_GUIDE,
    discover_assets,
    select_assets,
)

BASE = "https://assets.publishing.service.gov.uk/media/abc123/"

PAGE = f"""
<html><body>
<h1>Police recorded crime and outcomes open data tables</h1>
<p>Last updated 23 July 2026</p>

<h2>Outcomes open data</h2>
<section class="gem-c-attachment">
  <h3 class="gem-c-attachment__title">
    <a href="{BASE}outcomes-open-data-2014-15.csv">Outcomes open data year ending March 2015</a>
  </h3>
</section>
<section class="gem-c-attachment">
  <h3 class="gem-c-attachment__title">
    <a href="{BASE}outcomes-open-data-2025-26.xlsx">Outcomes open data year ending March 2026</a>
  </h3>
</section>

<h2>Police force area data tables</h2>
<section class="gem-c-attachment">
  <h3 class="gem-c-attachment__title">
    <a href="{BASE}prc-pfa-mar2026.csv">Police force area crime data to March 2026</a>
  </h3>
</section>

<h2>User guide</h2>
<section class="gem-c-attachment">
  <h3 class="gem-c-attachment__title">
    <a href="{BASE}open-data-user-guide.ods">Open data tables user guide</a>
  </h3>
</section>

<h2>Related</h2>
<p><a href="/government/statistics/crime-outcomes">A page, not a file</a></p>
<p><a href="{BASE}community-safety-partnership-2026.csv">Community safety partnership open data</a></p>
</body></html>
"""


def by_kind(assets, kind):
    return [asset for asset in assets if asset.kind == kind]


class TestDiscovery:
    def test_finds_every_data_file_and_no_html_pages(self):
        assets = discover_assets(PAGE)
        assert len(assets) == 5
        assert all(asset.url.startswith("https://") for asset in assets)

    def test_classifies_the_outcomes_series(self):
        outcomes = by_kind(discover_assets(PAGE), KIND_OUTCOMES)
        assert len(outcomes) == 2
        assert {asset.financial_year for asset in outcomes} == {"2014/15", "2025/26"}

    def test_classifies_the_force_area_crime_tables(self):
        crime = by_kind(discover_assets(PAGE), KIND_FORCE_AREA_CRIME)
        assert [asset.filename for asset in crime] == ["prc-pfa-mar2026.csv"]

    def test_classifies_the_user_guide(self):
        guide = by_kind(discover_assets(PAGE), KIND_USER_GUIDE)
        assert len(guide) == 1

    def test_resolves_relative_urls_against_the_landing_page(self):
        page = '<a href="/media/x/outcomes-open-data-2020-21.csv">Outcomes 2020/21</a>'
        asset = discover_assets(page)[0]
        assert asset.url.startswith("https://www.gov.uk/media/")

    def test_reads_a_financial_year_written_without_a_separator(self):
        page = '<a href="/x/outcomes201819.csv">Outcomes open data 201819</a>'
        assert discover_assets(page)[0].financial_year == "2018/19"

    def test_deduplicates_repeated_links(self):
        page = PAGE + f'<a href="{BASE}outcomes-open-data-2014-15.csv">again</a>'
        assert len(discover_assets(page)) == 5


class TestSelection:
    def test_drops_files_outside_the_three_kinds_we_use(self):
        selected = select_assets(discover_assets(PAGE), from_year=2014)
        assert len(selected) == 4
        assert "community-safety-partnership-2026.csv" not in {
            asset.filename for asset in selected
        }

    def test_respects_the_earliest_year_requested(self):
        selected = select_assets(discover_assets(PAGE), from_year=2020)
        outcomes = by_kind(selected, KIND_OUTCOMES)
        assert [asset.financial_year for asset in outcomes] == ["2025/26"]

    def test_keeps_an_outcomes_file_whose_year_cannot_be_read(self):
        page = '<a href="/x/outcomes-latest.csv">Outcomes open data, latest</a>'
        selected = select_assets(discover_assets(page), from_year=2014)
        assert len(selected) == 1
        assert selected[0].financial_year is None


class TestPublishedLinkTitles:
    """The exact titles the landing page carried on 23 July 2026.

    The published titles name the year a financial year ends in, which none of
    the original parsing handled, so every outcomes file came back undated and
    the earliest year filter silently did nothing.
    """

    REAL_TITLES = [
        ("Outcomes open data, year ending March 2026", "2025/26"),
        ("Outcomes open data, year ending March 2025", "2024/25"),
        ("Outcomes open data year ending March 2018", "2017/18"),
        ("Outcomes open data year ending March 2015", "2014/15"),
    ]

    @pytest.mark.parametrize("title,expected", REAL_TITLES)
    def test_year_ending_march_maps_to_a_financial_year(self, title, expected):
        from fetch import financial_years_covered

        assert financial_years_covered(title) == (expected,)

    def test_the_pre_2014_archive_is_read_as_a_range(self):
        from fetch import financial_years_covered

        covered = financial_years_covered(
            "Outcomes open data year ending March 2006 to year ending March 2014"
        )
        assert covered[0] == "2005/06"
        assert covered[-1] == "2013/14"
        assert len(covered) == 9

    def test_the_pre_2014_archive_is_not_selected(self):
        # It is published as ODS, which the transform does not read, and it is
        # wholly before the period this dashboard covers.
        page = (
            '<a href="/x/prc-outcomes-2006-2014.ods">Outcomes open data year '
            "ending March 2006 to year ending March 2014</a>"
        )
        assert select_assets(discover_assets(page), from_year=2014) == []

    def test_a_file_that_ends_inside_the_period_is_kept(self):
        page = (
            '<a href="/x/prc-outcomes.xlsx">Outcomes open data year ending '
            "March 2006 to year ending March 2016</a>"
        )
        assert len(select_assets(discover_assets(page), from_year=2014)) == 1

    def test_force_area_tables_are_classified_without_the_word_crime(self):
        page = (
            '<a href="/x/prc-pfa-mar2026.csv">Police force area data tables, '
            "year ending March 2026</a>"
        )
        assert discover_assets(page)[0].kind == KIND_FORCE_AREA_CRIME

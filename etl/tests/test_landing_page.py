"""The landing page as it actually was on 23 July 2026.

Every title here was read off the live page. The page lists a good deal more
than the two series this dashboard uses, and several of the others sit under the
same headings, so an earlier version that matched on the heading as well as the
title picked up seven files it should not have. Taking the alternate offences
file in particular would have double counted, because it holds outcome types
1a, 2a and 3a, which are already inside outcomes 1, 2 and 3.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fetch import (  # noqa: E402
    KIND_FORCE_AREA_CRIME,
    KIND_OTHER,
    KIND_OUTCOMES,
    discover_assets,
    select_assets,
)

# (filename, title) exactly as published.
REAL_PAGE = [
    ("prc-outcomes-open-data-mar2015-tables-241024.xlsx", "Outcomes open data year ending March 2015"),
    ("prc-outcomes-open-data-mar2016-tables-240724.xlsx", "Outcomes open data year ending March 2016"),
    ("prc-outcomes-open-data-mar2017-tables-240724.xlsx", "Outcomes open data year ending March 2017"),
    ("prc-outcomes-open-data-mar2018-tables-240724.xlsx", "Outcomes open data year ending March 2018"),
    ("prc-outcomes-open-data-mar2019-tables-240724.xlsx", "Outcomes open data, year ending March 2019"),
    ("prc-outcomes-open-data-mar2020-tables-240724.xlsx", "Outcomes open data, year ending March 2020"),
    ("prc-outcomes-open-data-mar2021-tables-240425.xlsx", "Outcomes open data, year ending March 2021"),
    ("prc-outcomes-open-data-mar2022-tables-240725.xlsx", "Outcomes open data, year ending March 2022"),
    ("prc-outcomes-open-data-mar2023-tables-230726.xlsx", "Outcomes open data, year ending March 2023"),
    ("prc-outcomes-open-data-mar2024-tables-230726.xlsx", "Outcomes open data, year ending March 2024"),
    ("prc-outcomes-open-data-mar2025-tables-230726.xlsx", "Outcomes open data, year ending March 2025"),
    ("prc-outcomes-open-data-mar2026-tables-230726.xlsx", "Outcomes open data, year ending March 2026"),
    ("prc-pfa-mar2013-onwards-tables-230726.ods", "Police recorded crime open data Police Force Area tables, year ending March 2013 onwards"),
    # Everything below must be passed over.
    ("prc-supplementary-crime-outcomes-metrics-230726.xlsx", "Supplementary crime outcomes metrics"),
    ("prc-outcomes-alternate-open-data-mar2017-to-mar2026-tables-230726.ods", "Outcomes for alternate offences open data, year ending March 2017 to year ending March 2026"),
    ("prc-subcodes-drug-offences-mar2021-to-mar2026.ods", "Police recorded crime subcodes for drugs offences, year ending March 2021 to year ending March 2026"),
    ("prc-firearms-outcomes-open-data-apr2024-to-mar2026-tables-230726.ods", "Crime outcomes for offences involving firearms in England and Wales open data, April 2024 to March 2026"),
    ("prc-knives_or_sharps-outcomes-open-data-apr2024-to-mar2026-tables-230726.ods", "Crime outcomes for offences involving knives or sharp instruments England and Wales open data, April 2024 to March 2026"),
    ("recrime-geo-pfa.csv", "Recorded crime data geographical reference table"),
    ("prc-subcodes-vawg-offences-mar2021-mar2026-230726.ods", "Police recorded crime subcodes for selected VAWG offences, from year ending March 2021 to year ending March 2026"),
]

PAGE_HTML = "".join(
    f'<h2>Outcomes open data</h2><a href="/media/x/{name}">{title}</a>'
    for name, title in REAL_PAGE
)

ASSETS = discover_assets(PAGE_HTML)
BY_TITLE = {asset.title: asset for asset in ASSETS}

EXPECTED_OUTCOMES = 12
EXPECTED_YEARS = [f"{year}/{(year + 1) % 100:02d}" for year in range(2014, 2026)]


class TestTheRealPage:
    def test_exactly_the_twelve_outcomes_files_are_taken(self):
        outcomes = [a for a in ASSETS if a.kind == KIND_OUTCOMES]
        assert len(outcomes) == EXPECTED_OUTCOMES

    def test_the_twelve_cover_every_year_from_2014_15(self):
        outcomes = [a for a in ASSETS if a.kind == KIND_OUTCOMES]
        assert sorted(a.financial_year for a in outcomes) == EXPECTED_YEARS

    def test_exactly_one_force_area_file_is_taken(self):
        crime = [a for a in ASSETS if a.kind == KIND_FORCE_AREA_CRIME]
        assert [a.filename for a in crime] == ["prc-pfa-mar2013-onwards-tables-230726.ods"]

    @pytest.mark.parametrize(
        "title",
        [
            "Supplementary crime outcomes metrics",
            "Outcomes for alternate offences open data, year ending March 2017 to year ending March 2026",
            "Police recorded crime subcodes for drugs offences, year ending March 2021 to year ending March 2026",
            "Crime outcomes for offences involving firearms in England and Wales open data, April 2024 to March 2026",
            "Crime outcomes for offences involving knives or sharp instruments England and Wales open data, April 2024 to March 2026",
            "Recorded crime data geographical reference table",
            "Police recorded crime subcodes for selected VAWG offences, from year ending March 2021 to year ending March 2026",
        ],
    )
    def test_everything_else_is_passed_over(self, title):
        assert BY_TITLE[title].kind == KIND_OTHER

    def test_the_alternate_offences_file_says_why_it_is_passed_over(self):
        # It holds outcome types 1a, 2a and 3a. Adding it would double count.
        asset = BY_TITLE[
            "Outcomes for alternate offences open data, year ending March 2017 "
            "to year ending March 2026"
        ]
        assert "1a" in asset.reason

    def test_every_passed_over_file_carries_a_reason(self):
        for asset in ASSETS:
            if asset.kind == KIND_OTHER:
                assert asset.reason, f"{asset.title} was dropped without a reason"

    def test_selection_takes_thirteen_files(self):
        selected = select_assets(ASSETS, from_year=2014)
        assert len(selected) == EXPECTED_OUTCOMES + 1

    def test_a_heading_cannot_pull_in_a_file_the_title_rejects(self):
        # Every anchor in PAGE_HTML sits under an "Outcomes open data" heading,
        # including the ones that are not the series. Matching on the heading is
        # what caused the over-selection this test exists to prevent.
        assert BY_TITLE["Recorded crime data geographical reference table"].kind == KIND_OTHER

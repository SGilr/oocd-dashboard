"""Tests for the classification and normalisation the whole pipeline rests on."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import (  # noqa: E402
    CANONICAL_FORCES,
    CHARGE_TYPES,
    OOCD_TYPES,
    POSITIVE_TYPES,
    OUTCOME_LABELS,
    HeaderMappingError,
    build_header_map,
    canonical_force,
    classify_outcome,
    force_slug,
    normalise_financial_year,
    normalise_header,
    normalise_quarter,
    to_int,
    truthy_flag,
)


class TestOutcomeClassification:
    def test_six_out_of_court_types(self):
        assert OOCD_TYPES == (2, 3, 6, 7, 8, 22)

    def test_taken_into_consideration_is_not_a_disposal(self):
        # Outcome 4 is an admission recorded alongside a prosecution. Sweeping
        # it in would inflate every out of court figure on the site.
        assert 4 not in OOCD_TYPES
        assert 4 not in POSITIVE_TYPES
        assert classify_outcome(4) == "other"

    def test_positive_is_charge_plus_the_six(self):
        assert POSITIVE_TYPES == (1, 2, 3, 6, 7, 8, 22)
        assert set(POSITIVE_TYPES) == set(CHARGE_TYPES) | set(OOCD_TYPES)

    @pytest.mark.parametrize("outcome_type", OOCD_TYPES)
    def test_out_of_court_types_classify_as_oocd(self, outcome_type):
        assert classify_outcome(outcome_type) == "oocd"

    def test_charge_classifies_as_charge(self):
        assert classify_outcome(1) == "charge"

    @pytest.mark.parametrize("outcome_type", [5, 9, 10, 15, 16, 18, 21])
    def test_non_positive_types_classify_as_other(self, outcome_type):
        assert classify_outcome(outcome_type) == "other"


class TestForces:
    def test_forty_four_forces(self):
        assert len(CANONICAL_FORCES) == 44
        assert len(set(CANONICAL_FORCES)) == 44

    @pytest.mark.parametrize(
        "published,expected",
        [
            ("British Transport Police", "British Transport Police"),
            ("Metropolitan Police Service", "Metropolitan Police"),
            ("Avon and Somerset Constabulary", "Avon and Somerset"),
            ("City of London Police", "City of London"),
            ("Devon & Cornwall", "Devon and Cornwall"),
            ("Hampshire and Isle of Wight", "Hampshire"),
            ("  West   Yorkshire  ", "West Yorkshire"),
            ("Action Fraud", "Action Fraud"),
        ],
    )
    def test_published_names_map_to_canonical(self, published, expected):
        assert canonical_force(published) == expected

    def test_unrecognised_name_returns_none_rather_than_guessing(self):
        assert canonical_force("Ambridge Constabulary") is None
        assert canonical_force("") is None
        assert canonical_force(None) is None

    def test_every_canonical_name_maps_to_itself(self):
        for force in CANONICAL_FORCES:
            assert canonical_force(force) == force

    def test_slugs_are_unique_and_url_safe(self):
        slugs = [force_slug(force) for force in CANONICAL_FORCES]
        assert len(set(slugs)) == 44
        for slug in slugs:
            assert slug == slug.lower()
            assert " " not in slug


class TestFinancialYears:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("2014/15", "2014/15"),
            ("2020-21", "2020/21"),
            ("2019/2020", "2019/20"),
            ("Financial year 2023/24", "2023/24"),
        ],
    )
    def test_parses_the_forms_that_appear_in_the_files(self, raw, expected):
        assert normalise_financial_year(raw) == expected

    @pytest.mark.parametrize("raw", ["2014/16", "not a year", "", None, "2014"])
    def test_refuses_what_it_cannot_read(self, raw):
        assert normalise_financial_year(raw) is None

    @pytest.mark.parametrize(
        "raw,expected", [("Q1", 1), ("Quarter 3", 3), (4, 4), ("2", 2)]
    )
    def test_quarters(self, raw, expected):
        assert normalise_quarter(raw) == expected

    def test_quarter_refuses_nonsense(self):
        assert normalise_quarter("Q9") is None
        assert normalise_quarter(None) is None


class TestHeaderIntrospection:
    published_headers = [
        "Financial Year",
        "Financial Quarter",
        "Force Name",
        "Offence Code",
        "Offence Description",
        "Offence Group",
        "Offence Subgroup",
        "Offence Code Expired",
        "Outcome Type",
        "Outcome Description",
        "Outcome Group",
        "Number of Outcomes for offences that were recorded in the quarter",
        "Number of Outcomes for investigations that were closed in the quarter",
    ]

    def test_maps_the_published_headers(self):
        header_map = build_header_map(self.published_headers)
        assert header_map.column("count_closed") == (
            "Number of Outcomes for investigations that were closed in the quarter"
        )
        assert header_map.column("force_name") == "Force Name"
        assert header_map.unmapped == ()

    def test_tolerates_case_spacing_and_punctuation_differences(self):
        variant = [
            "FINANCIAL  YEAR",
            "financial_quarter",
            "Force name",
            "Offence code",
            "Outcome Type",
            "Outcomes for offences that were recorded in the quarter",
            "Outcomes for investigations closed in the quarter",
        ]
        header_map = build_header_map(variant)
        assert set(header_map.by_field) >= {
            "financial_year",
            "financial_quarter",
            "force_name",
            "count_closed",
            "count_recorded",
        }

    def test_missing_required_field_fails_loudly(self):
        headers = [h for h in self.published_headers if h != "Force Name"]
        with pytest.raises(HeaderMappingError, match="force_name"):
            build_header_map(headers)

    def test_unmapped_header_fails_loudly_rather_than_dropping_a_column(self):
        headers = self.published_headers + ["Some New Column The Home Office Added"]
        with pytest.raises(HeaderMappingError, match="could not be mapped"):
            build_header_map(headers)

    def test_unmapped_header_can_be_allowed_deliberately(self):
        headers = self.published_headers + ["Some New Column"]
        header_map = build_header_map(headers, allow_unmapped=True)
        assert header_map.unmapped == ("Some New Column",)

    def test_two_headers_claiming_one_field_fails(self):
        headers = self.published_headers + ["Force"]
        with pytest.raises(HeaderMappingError, match="same field"):
            build_header_map(headers)

    def test_normalise_header_ignores_non_breaking_spaces(self):
        assert normalise_header("Force Name") == "force name"


class TestCountCells:
    @pytest.mark.parametrize(
        "raw,expected",
        [(None, 0), ("", 0), (":", 0), ("1,234", 1234), (7, 7), (7.0, 7), ("12", 12)],
    )
    def test_reads_the_cell_forms_that_appear(self, raw, expected):
        assert to_int(raw) == expected

    def test_refuses_a_fractional_count(self):
        with pytest.raises(ValueError):
            to_int(1.5)

    def test_refuses_a_boolean(self):
        with pytest.raises(ValueError):
            to_int(True)

    @pytest.mark.parametrize("raw,expected", [("Yes", True), ("No", False), (None, False), ("", False)])
    def test_expired_flag(self, raw, expected):
        assert truthy_flag(raw) is expected


class TestPublishedFileQuirks:
    """Behaviour confirmed against the year ending March 2026 file.

    Each of these was a defect found by running the ETL against the real
    published workbook rather than against an assumption about it.
    """

    def test_outcome_type_zero_is_not_an_outcome(self):
        from common import NOT_ASSIGNED_TYPE, OOCD_TYPES, POSITIVE_TYPES

        assert NOT_ASSIGNED_TYPE == 0
        assert 0 not in OOCD_TYPES
        assert 0 not in POSITIVE_TYPES
        assert classify_outcome(0) == "other"

    def test_outcome_type_zero_has_a_label(self):
        assert OUTCOME_LABELS[0] == "Not yet assigned an outcome"

    def test_expired_code_marker_in_a_count_cell_reads_as_zero(self):
        # The recorded column carries this exact string against retired offence
        # codes. Before this was handled the transform crashed on it.
        assert to_int("N/A - Offence code expired") == 0

    def test_bare_not_applicable_reads_as_zero(self):
        # The closed column carries this against outcome type 0.
        assert to_int("N/A") == 0
        assert to_int("n/a") == 0

    def test_an_unreadable_count_raises_rather_than_becoming_zero(self):
        with pytest.raises(ValueError, match="Cannot read"):
            to_int("some new marker")

    def test_expired_flag_is_a_lower_case_x(self):
        # The published flag is 'x', not 'Yes'. Reading it as false meant every
        # retired code looked current.
        assert truthy_flag("x") is True
        assert truthy_flag("X") is True
        assert truthy_flag(None) is False

    def test_city_of_london_is_published_reversed(self):
        assert canonical_force("London, City of") == "City of London"

    def test_essential_types_are_the_ones_classification_needs(self):
        from common import CHARGE_TYPES, ESSENTIAL_TYPES, OOCD_TYPES

        assert set(ESSENTIAL_TYPES) == set(CHARGE_TYPES) | set(OOCD_TYPES)
        # Type 19 is absent from the year ending March 2026 file, so it must not
        # be treated as essential or the build could never pass.
        assert 19 not in ESSENTIAL_TYPES


class TestFalsyZero:
    """Outcome type 0 is a real value, and zero is falsy.

    `str(cell or "")` silently turned 32,384 rows of outcome type 0 into blanks
    that then failed to parse and were dropped without a word. That is exactly
    the silent drop this pipeline is built to prevent, so it is pinned here.
    """

    def test_zero_survives(self):
        from common import text_of

        assert text_of(0) == "0"
        assert int(text_of(0)) == 0

    def test_none_and_blank_give_the_default(self):
        from common import text_of

        assert text_of(None) == ""
        assert text_of("   ") == ""
        assert text_of(None, "Unclassified") == "Unclassified"
        assert text_of("", "Unclassified") == "Unclassified"

    def test_ordinary_values_are_stripped(self):
        from common import text_of

        assert text_of("  105A  ") == "105A"
        assert text_of(22) == "22"

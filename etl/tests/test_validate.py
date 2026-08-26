"""Tests that the build gates actually fire.

A validation script that never fails is worse than none, because it reads as
assurance. These tests break the derived tables on purpose and check that the
right gate catches it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import CANONICAL_FORCES, COUNT_BASES, OOCD_TYPES, OUTCOME_LABELS  # noqa: E402
from validate import (  # noqa: E402
    Report,
    check_forces,
    check_negative_counts,
    check_outcome_type_coverage,
    check_provenance,
    check_totals_reconcile,
    check_year_on_year,
)

FRAUD_VARIANTS = ("all", "ex_fraud")


def make_row(force="Kent", fy="2020/21", oocd_counts=None, charge=100, other=500):
    """Build one internally consistent derived row."""
    oocd_counts = oocd_counts or dict.fromkeys(OOCD_TYPES, 10)
    row = {"force": force, "slug": force.lower(), "fy": fy, "q": 1}
    for basis in COUNT_BASES:
        for variant in FRAUD_VARIANTS:
            prefix = f"{basis}_{variant}_"
            oocd_total = 0
            for outcome_type in OOCD_TYPES:
                value = oocd_counts[outcome_type]
                row[f"{prefix}t{outcome_type}"] = value
                oocd_total += value
            row[f"{prefix}t1"] = charge
            row[f"{prefix}oocd"] = oocd_total
            row[f"{prefix}positive"] = oocd_total + charge
            row[f"{prefix}assigned"] = oocd_total + charge + other
    return row


def tables_from(rows, name="force_year"):
    empty = {"meta": {}, "rows": []}
    tables = {
        key: dict(empty)
        for key in (
            "force_quarter",
            "force_year",
            "national_quarter",
            "national_year",
            "force_offence_year",
        )
    }
    tables[name] = {"meta": {}, "rows": rows}
    return tables


class TestTotalsReconcile:
    def test_consistent_rows_pass(self):
        report = Report()
        check_totals_reconcile(tables_from([make_row()]), report)
        assert report.failures == []

    def test_out_of_court_total_that_does_not_match_its_components_fails(self):
        row = make_row()
        row["closed_all_oocd"] += 7
        report = Report()
        check_totals_reconcile(tables_from([row]), report)
        assert any(f["check"] == "totals_reconcile" for f in report.failures)

    def test_positive_total_missing_the_charge_comparator_fails(self):
        row = make_row()
        row["closed_all_positive"] -= row["closed_all_t1"]
        report = Report()
        check_totals_reconcile(tables_from([row]), report)
        assert report.failures

    def test_positive_outcomes_exceeding_all_assigned_fails(self):
        row = make_row(other=0)
        row["closed_all_assigned"] = row["closed_all_positive"] - 1
        report = Report()
        check_totals_reconcile(tables_from([row]), report)
        assert report.failures

    def test_excluding_fraud_producing_a_larger_total_fails(self):
        row = make_row()
        row["closed_ex_fraud_assigned"] = row["closed_all_assigned"] + 1
        report = Report()
        check_totals_reconcile(tables_from([row]), report)
        assert report.failures


class TestForceCoverage:
    def test_all_forty_four_pass(self):
        report = Report()
        check_forces({"forces": list(CANONICAL_FORCES)}, report)
        assert report.failures == []

    def test_a_missing_force_fails(self):
        report = Report()
        check_forces({"forces": list(CANONICAL_FORCES[:-1])}, report)
        assert report.failures
        assert "British Transport Police" in report.failures[0]["missing"]

    def test_an_unrecognised_force_name_fails_rather_than_being_dropped(self):
        report = Report()
        check_forces(
            {"forces": list(CANONICAL_FORCES), "unknown_force_names": {"Ambridge": 12}},
            report,
        )
        assert any(f["check"] == "force_names" for f in report.failures)


class TestOutcomeTypeCoverage:
    def test_all_twenty_two_pass(self):
        report = Report()
        check_outcome_type_coverage(
            {"outcome_type_years": {str(t): ["2020/21"] for t in OUTCOME_LABELS}},
            report,
        )
        assert report.failures == []

    def test_a_missing_outcome_type_fails(self):
        years = {str(t): ["2020/21"] for t in OUTCOME_LABELS if t != 7}
        report = Report()
        check_outcome_type_coverage({"outcome_type_years": years}, report)
        assert report.failures


class TestNegativeCounts:
    def test_a_negative_source_count_fails(self):
        report = Report()
        check_negative_counts({"negative_count_rows": 3}, tables_from([]), report)
        assert report.failures

    def test_a_negative_derived_count_fails(self):
        row = make_row()
        row["closed_all_t8"] = -1
        report = Report()
        check_negative_counts({}, tables_from([row]), report)
        assert report.failures


class TestYearOnYear:
    def test_a_large_move_is_flagged_not_failed(self):
        rows = [
            make_row(fy="2020/21", oocd_counts=dict.fromkeys(OOCD_TYPES, 100)),
            make_row(fy="2021/22", oocd_counts=dict.fromkeys(OOCD_TYPES, 400)),
        ]
        report = Report()
        check_year_on_year(tables_from(rows), report)
        assert report.failures == []
        assert len(report.flags) == 1
        assert report.flags[0]["change_pct"] == 300.0

    def test_a_small_series_is_not_flagged(self):
        rows = [
            make_row(fy="2020/21", oocd_counts=dict.fromkeys(OOCD_TYPES, 1)),
            make_row(fy="2021/22", oocd_counts=dict.fromkeys(OOCD_TYPES, 8)),
        ]
        report = Report()
        check_year_on_year(tables_from(rows), report)
        assert report.flags == []

    def test_a_modest_move_is_not_flagged(self):
        rows = [
            make_row(fy="2020/21", oocd_counts=dict.fromkeys(OOCD_TYPES, 100)),
            make_row(fy="2021/22", oocd_counts=dict.fromkeys(OOCD_TYPES, 110)),
        ]
        report = Report()
        check_year_on_year(tables_from(rows), report)
        assert report.flags == []


class TestProvenance:
    def test_live_data_passes_without_a_flag(self):
        report = Report()
        check_provenance({"provenance": "home_office_open_data"}, report)
        assert report.failures == [] and report.flags == []

    def test_fixture_data_is_flagged_so_it_cannot_be_published_unnoticed(self):
        report = Report()
        check_provenance({"provenance": "fixture"}, report)
        assert report.flags and report.failures == []

    def test_an_unrecognised_provenance_fails(self):
        report = Report()
        check_provenance({"provenance": "somewhere"}, report)
        assert report.failures

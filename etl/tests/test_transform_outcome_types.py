"""Outcome types the classification has not seen must stop the build.

The counting rules gain outcome types from time to time: 23 and 24, child and
adult deferred prosecution, arrived in April 2026. A type the ETL did not know
about would otherwise fall into "other" and out of every out of court figure
without anyone noticing, which is the silent drop this pipeline exists to
prevent.
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transform import Aggregator, process_outcomes_file  # noqa: E402

HEADER = [
    "Financial Year",
    "Financial Quarter",
    "Force Name",
    "Offence Code",
    "Offence Group",
    "Outcome Type",
    "Number of outcomes for offences that were recorded in the quarter",
    "Number of outcomes for investigations that were closed in the quarter",
]


def write_rows(path: Path, rows: list[list[object]]) -> Path:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


def test_deferred_prosecution_types_count_as_out_of_court(tmp_path):
    path = write_rows(
        tmp_path / "outcomes.csv",
        [
            ["2026/27", 1, "Kent", "8A", "Violence against the person", 22, 5, 7],
            ["2026/27", 1, "Kent", "8A", "Violence against the person", 23, 2, 3],
            ["2026/27", 1, "Kent", "8A", "Violence against the person", 24, 4, 6],
        ],
    )
    aggregator = Aggregator()
    process_outcomes_file(path, aggregator, [])
    assert not aggregator.unknown_outcome_types
    bucket = aggregator.quarter[("Kent", "2026/27", 1)]["closed"]["all"]
    assert bucket["t23"] == 3
    assert bucket["t24"] == 6
    assert bucket["oocd"] == 16
    assert bucket["positive"] == 16


def test_an_unknown_outcome_type_is_held_back_and_counted(tmp_path):
    path = write_rows(
        tmp_path / "outcomes.csv",
        [
            ["2026/27", 1, "Kent", "8A", "Violence against the person", 8, 5, 7],
            ["2026/27", 1, "Kent", "8A", "Violence against the person", 25, 2, 3],
        ],
    )
    aggregator = Aggregator()
    process_outcomes_file(path, aggregator, [])
    assert dict(aggregator.unknown_outcome_types) == {25: 1}
    bucket = aggregator.quarter[("Kent", "2026/27", 1)]["closed"]["all"]
    # The unknown row has not been absorbed into any total.
    assert bucket["assigned"] == 7

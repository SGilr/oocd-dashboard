#!/usr/bin/env python3
"""Generate synthetic raw files, so the pipeline can be exercised offline.

The fixtures have the shape of the published files: the same headers, the same
44 forces, the same outcome types, the same two count columns. The numbers are
invented. They exist to prove that fetch, transform and validate work end to
end, and to let the site be built and reviewed before the real extract runs.

The manifest this writes records provenance "fixture". Every part of the
pipeline reads that field, validate.py flags it, and the site renders a banner
on every page saying the figures are not real. A build carrying fixture
provenance must not be published.

Usage:
    python etl/make_fixtures.py
    python etl/make_fixtures.py --years 2014 2026
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    CANONICAL_FORCES,
    OUTCOME_LABELS,
    resolve_data_root,
    write_json,
)

PATHS = resolve_data_root("fixture")

# The published header wording and column order, taken from the year ending
# March 2026 file. Nothing in the ETL is positional, but the fixture matching the
# published file means a header change shows up in CI rather than in production.
OUTCOMES_HEADERS = [
    "Financial Year",
    "Financial Quarter",
    "Force Name",
    "Offence Code",
    "Offence Description",
    "Offence Group",
    "Offence Subgroup",
    "Offence code expired",
    "Outcome Type",
    "Outcome Description",
    "Outcome Group",
    "Outcomes for offences that were recorded in the quarter",
    "Outcomes for investigations closed in the quarter",
]

CRIME_HEADERS = [
    "Financial Year",
    "Financial Quarter",
    "Force Name",
    "Offence Group",
    "Offence Subgroup",
    "Number of Offences",
]

# A small offence structure, enough to exercise the fraud toggle and the
# expired code flag without generating a file too large to work with.
OFFENCES = [
    ("008", "Violence with injury", "Violence against the person", "Violence with injury", False),
    ("105A", "Common assault", "Violence against the person", "Violence without injury", False),
    ("049", "Theft from the person", "Theft offences", "Theft from the person", False),
    ("046", "Shoplifting", "Theft offences", "Shoplifting", False),
    ("092D", "Possession of cannabis", "Drug offences", "Possession of drugs", False),
    ("NFIB1", "Banking and credit industry fraud", "Fraud offences", "Fraud: NFIB", False),
    ("053", "Retired vehicle interference code", "Theft offences", "Vehicle offences", True),
]

OUTCOME_GROUPS = {
    0: "Not yet assigned an outcome",
    1: "Charged/Summonsed",
    11: "Evidential difficulties",
    12: "Evidential difficulties",
    13: "Evidential difficulties",
    14: "Evidential difficulties",
    17: "Evidential difficulties",
    19: "Investigation complete - no suspect identified",
    20: "Other agency dealing",
    21: "Evidential difficulties",
    2: "Out-of-court (formal)",
    3: "Out-of-court (formal)",
    4: "Taken into consideration",
    5: "Investigation complete - no suspect identified",
    6: "Out-of-court (formal)",
    7: "Out-of-court (informal)",
    8: "Out-of-court (informal)",
    9: "Evidential difficulties",
    10: "Evidential difficulties",
    15: "Evidential difficulties",
    16: "Evidential difficulties",
    18: "Investigation complete - no suspect identified",
    22: "Diversionary activity",
}

# Force size multipliers, so the fixture has a plausible spread rather than 44
# identical forces. Invented, and only used to shape fixture numbers.
FORCE_SCALE = {force: 0.4 + (index % 11) * 0.35 for index, force in enumerate(CANONICAL_FORCES)}
FORCE_SCALE["Metropolitan Police"] = 8.0
FORCE_SCALE["City of London"] = 0.15
FORCE_SCALE["British Transport Police"] = 0.6


def outcome_types_for(financial_year_start: int) -> list[int]:
    """Outcome 22 only exists from 2019/20, as in the real series."""
    # Type 0, not yet assigned an outcome, is present in the published files and
    # must never enter a total. Type 19 is absent from the year ending March
    # 2026 file, so the fixture leaves it out of recent years too.
    types = [0] + [t for t in range(1, 19)]
    if financial_year_start < 2020:
        types.append(19)
    types += [20, 21]
    if financial_year_start >= 2019:
        types.append(22)
    return types


def generate_outcomes(year_start: int, rng: random.Random) -> list[list[object]]:
    financial_year = f"{year_start}/{(year_start + 1) % 100:02d}"
    rows: list[list[object]] = []
    for force in CANONICAL_FORCES:
        scale = FORCE_SCALE[force]
        published_name = "London, City of" if force == "City of London" else force
        for quarter in (1, 2, 3, 4):
            for code, description, group, subgroup, expired in OFFENCES:
                if expired and year_start >= 2019:
                    continue
                if group == "Fraud offences" and force == "British Transport Police":
                    continue
                for outcome_type in outcome_types_for(year_start):
                    # West Yorkshire operates a restricted disposal set, so the
                    # fixture reproduces that pattern and the annotation has
                    # something to sit against.
                    if force == "West Yorkshire" and outcome_type in (2, 3, 6, 7):
                        continue
                    base = {
                        1: 260, 2: 22, 3: 34, 4: 18, 5: 6, 6: 12, 7: 9, 8: 74,
                        9: 30, 10: 26, 11: 2, 12: 3, 13: 2, 14: 120, 15: 210,
                        16: 190, 17: 4, 18: 640, 19: 5, 20: 14, 21: 8, 22: 40,
                        0: 300,
                    }[outcome_type]
                    if outcome_type == 22 and year_start < 2021:
                        # Voluntary recording: most forces record nothing.
                        base = base if rng.random() < 0.35 else 0
                    if group == "Fraud offences":
                        base = int(base * 0.3)
                    closed = int(base * scale * rng.uniform(0.7, 1.3))
                    recorded = int(closed * rng.uniform(0.6, 0.95))

                    if outcome_type == 0:
                        # Type 0 has no closed count: an offence with no outcome
                        # yet cannot belong to a closed investigation. The
                        # published files write N/A here.
                        closed_cell: object = "N/A"
                        # A force that reclassifies more offences in a quarter
                        # than it records produces a small negative, as
                        # Humberside does in the year ending March 2026.
                        if force == "Humberside" and code == "049":
                            recorded = -quarter
                        recorded_cell: object = recorded
                    else:
                        closed_cell = closed
                        recorded_cell = recorded
                        if closed == 0 and recorded == 0:
                            continue

                    if expired:
                        # An expired code cannot take new recordings. The
                        # published files write this exact string.
                        recorded_cell = "N/A - Offence code expired"

                    # Greater Manchester did not supply data for part of
                    # 2019/20 after an IT change. The published files mark it
                    # "N/A - data not provided", which means missing rather
                    # than zero, and the fixture reproduces it so the handling
                    # is exercised in the tests.
                    if force == "Greater Manchester" and year_start == 2019 and quarter >= 2:
                        recorded_cell = "N/A - data not provided"
                        closed_cell = "N/A - data not provided"

                    rows.append(
                        [
                            financial_year,
                            f"Q{quarter}",
                            published_name,
                            code,
                            description,
                            group,
                            subgroup,
                            # The published flag is a lower case x, not "Yes".
                            "x" if expired else None,
                            outcome_type,
                            OUTCOME_LABELS[outcome_type],
                            OUTCOME_GROUPS.get(outcome_type, "Other"),
                            recorded_cell,
                            closed_cell,
                        ]
                    )
    return rows


def generate_crime(year_start: int, rng: random.Random) -> list[list[object]]:
    financial_year = f"{year_start}/{(year_start + 1) % 100:02d}"
    rows: list[list[object]] = []
    for force in CANONICAL_FORCES:
        # British Transport Police leaves the published force area tables after
        # 2014/15, so from then on it has no recorded crime denominator at all.
        # The fixture reproduces that, so the site's handling of a force with no
        # denominator is exercised by the tests rather than only in production.
        if force == "British Transport Police" and year_start >= 2015:
            continue
        scale = FORCE_SCALE[force]
        for quarter in (1, 2, 3, 4):
            for _, _, group, subgroup, _ in OFFENCES:
                rows.append(
                    [
                        financial_year,
                        f"Q{quarter}",
                        force,
                        group,
                        subgroup,
                        int(9000 * scale * rng.uniform(0.8, 1.2)),
                    ]
                )
    return rows


def write_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs=2, type=int, default=[2014, 2025])
    parser.add_argument("--seed", type=int, default=20260826)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    first, last = args.years
    entries: list[dict] = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for year_start in range(first, last + 1):
        label = f"{year_start}-{(year_start + 1) % 100:02d}"

        outcomes_path = PATHS.raw / f"fixture-outcomes-open-data-{label}.csv"
        write_csv(outcomes_path, OUTCOMES_HEADERS, generate_outcomes(year_start, rng))
        entries.append(
            {
                "kind": "outcomes_open_data",
                "filename": outcomes_path.name,
                "title": f"FIXTURE outcomes open data {year_start}/{(year_start + 1) % 100:02d}",
                "section": "Synthetic fixture, not published data",
                "financial_year": f"{year_start}/{(year_start + 1) % 100:02d}",
                "url": None,
                "retrieved_at": now,
                "size_bytes": outcomes_path.stat().st_size,
                "sha256": sha256_of(outcomes_path),
                "reused_local_copy": False,
            }
        )

        crime_path = PATHS.raw / f"fixture-pfa-crime-{label}.csv"
        write_csv(crime_path, CRIME_HEADERS, generate_crime(year_start, rng))
        entries.append(
            {
                "kind": "police_force_area_crime",
                "filename": crime_path.name,
                "title": f"FIXTURE police force area crime {year_start}/{(year_start + 1) % 100:02d}",
                "section": "Synthetic fixture, not published data",
                "financial_year": f"{year_start}/{(year_start + 1) % 100:02d}",
                "url": None,
                "retrieved_at": now,
                "size_bytes": crime_path.stat().st_size,
                "sha256": sha256_of(crime_path),
                "reused_local_copy": False,
            }
        )

    manifest = {
        "provenance": "fixture",
        "landing_page": None,
        "licence": "Not applicable, these numbers are invented",
        "attribution": (
            "SYNTHETIC FIXTURE DATA. These figures are generated by "
            "etl/make_fixtures.py to exercise the pipeline. They are not "
            "police recorded crime statistics and must not be published or "
            "cited."
        ),
        "generated_at": now,
        "earliest_financial_year_requested": first,
        "files": sorted(entries, key=lambda entry: entry["filename"]),
    }
    write_json(PATHS.manifest, manifest)

    print(f"Wrote {len(entries)} fixture files to {PATHS.raw}")
    print(f"Manifest written to {PATHS.manifest}")
    print("Provenance: fixture. A build carrying it must not be published.")
    print("Next: python etl/transform.py --data-root fixture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

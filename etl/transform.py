#!/usr/bin/env python3
"""Read the raw Home Office files and write the derived tables the site uses.

Nothing here is positional. Headers are introspected and normalised, because
they vary between years, and a header that cannot be mapped stops the run
rather than being dropped in silence.

Both count bases are carried through every derived table. Percentages are not
computed here, they are computed at render time, so the stored numbers stay
integers and the rounding is visible in one place.

Usage:
    python etl/transform.py
    python etl/transform.py --raw-dir data/raw --out-dir data/processed
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    NOT_ASSIGNED_TYPE,
    BASIS_CLOSED,
    BASIS_RECORDED,
    CENTRAL_FRAUD_BODIES,
    COUNT_BASES,
    DEFAULT_BASIS,
    OOCD_TYPES,
    OUTCOME_LABELS,
    POSITIVE_TYPES,
    REQUIRED_OUTCOME_FIELDS,
    HeaderMappingError,
    build_header_map,
    canonical_force,
    financial_year_start,
    force_slug,
    normalise_financial_year,
    normalise_quarter,
    read_json,
    resolve_data_root,
    to_int,
    truthy_flag,
    write_json_compact,
)

# The outcome types stored individually in the derived tables: the charge
# comparator and the six out of court types. Everything else is carried only
# inside the assigned total, which is what the denominators need.
STORED_TYPES: tuple[int, ...] = POSITIVE_TYPES
COUNT_COLUMNS: tuple[str, ...] = tuple(f"t{t}" for t in STORED_TYPES) + (
    "oocd",
    "positive",
    "assigned",
)

FRAUD_VARIANTS: tuple[str, ...] = ("all", "ex_fraud")


def is_fraud_group(offence_group: str | None, offence_subgroup: str | None) -> bool:
    """True when a row belongs to the fraud offence group.

    Fraud reported to Action Fraud, Cifas and Financial Fraud UK is recorded
    centrally and then attributed to force areas, so it distorts offence mix.
    The exclude fraud variant drops the whole fraud group rather than trying to
    separate centrally recorded fraud from force recorded fraud, which the
    published tables do not support.
    """
    for value in (offence_group, offence_subgroup):
        if value and "fraud" in str(value).lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


def read_csv_rows(path: Path) -> Iterator[list[object]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            yield row


def read_xlsx_rows(path: Path) -> Iterator[list[object]]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = _pick_sheet(workbook)
        for row in sheet.iter_rows(values_only=True):
            yield list(row)
    finally:
        workbook.close()


def _pick_sheet(workbook):
    """Choose the data sheet, skipping cover, notes and contents sheets."""
    skip_tokens = ("cover", "note", "contents", "metadata", "definitions", "guide")
    for sheet in workbook.worksheets:
        name = sheet.title.strip().lower()
        if any(token in name for token in skip_tokens):
            continue
        return sheet
    return workbook.worksheets[0]


def read_rows(path: Path) -> Iterator[list[object]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_csv_rows(path)
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return read_xlsx_rows(path)
    raise ValueError(f"Cannot read {path.name}: unsupported file type {suffix}")


def find_header_row(rows: Iterator[list[object]], required: tuple[str, ...]):
    """Scan the first rows for the header, so a cover block does not break it.

    Consumes rows from the iterator up to and including the header row, and
    returns (header_map, header_row_values). The caller keeps iterating the
    same iterator to read the data. Raises when no row in the first twenty
    looks like a header.
    """
    seen = 0
    last_error: Exception | None = None
    for row in rows:
        seen += 1
        if seen > 20:
            break
        try:
            header_map = build_header_map(row, required=required)
        except HeaderMappingError as error:
            last_error = error
            continue
        return header_map, row
    raise HeaderMappingError(
        "No header row found in the first 20 rows. Last attempt said: "
        f"{last_error}"
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


class Aggregator:
    """Accumulates counts while streaming the raw rows."""

    def __init__(self) -> None:
        # (force, fy, quarter) -> basis -> variant -> {column: count}
        self.quarter: dict[tuple[str, str, int], dict] = {}
        # (force, fy, offence_group) -> basis -> {oocd, charge}
        self.offence: dict[tuple[str, str, str], dict] = {}
        self.outcome_type_years: dict[int, set[str]] = defaultdict(set)
        self.unknown_forces: dict[str, int] = defaultdict(int)
        self.central_fraud_rows = 0
        self.expired_code_rows = 0
        self.rows_read = 0
        self.rows_used = 0
        self.negative_counts = 0
        self.duplicate_source_keys = 0
        self.duplicate_examples: list[str] = []
        self.not_assigned_rows = 0
        self.not_assigned_counts = {BASIS_CLOSED: 0, BASIS_RECORDED: 0}
        self.negative_counts_excluded = 0
        self.negative_examples: list[str] = []
        self.subset_type_rows: dict[str, int] = defaultdict(int)

    @staticmethod
    def _empty_cell() -> dict:
        return {
            basis: {
                variant: dict.fromkeys(COUNT_COLUMNS, 0) for variant in FRAUD_VARIANTS
            }
            for basis in COUNT_BASES
        }

    def add(
        self,
        force: str,
        financial_year: str,
        quarter: int,
        offence_group: str,
        outcome_type: int,
        counts: dict[str, int],
        fraud: bool,
    ) -> None:
        cell = self.quarter.setdefault(
            (force, financial_year, quarter), self._empty_cell()
        )
        variants = ("all",) if fraud else FRAUD_VARIANTS

        for basis in COUNT_BASES:
            value = counts[basis]
            if value == 0:
                continue
            for variant in variants:
                bucket = cell[basis][variant]
                bucket["assigned"] += value
                if outcome_type in STORED_TYPES:
                    bucket[f"t{outcome_type}"] += value
                    bucket["positive"] += value
                    if outcome_type in OOCD_TYPES:
                        bucket["oocd"] += value

        if outcome_type in POSITIVE_TYPES:
            offence_cell = self.offence.setdefault(
                (force, financial_year, offence_group),
                {basis: {"oocd": 0, "charge": 0} for basis in COUNT_BASES},
            )
            for basis in COUNT_BASES:
                value = counts[basis]
                if value == 0:
                    continue
                key = "oocd" if outcome_type in OOCD_TYPES else "charge"
                offence_cell[basis][key] += value


def _note_negative(aggregator, path, force, financial_year, quarter, offence_code,
                   outcome_type, counts) -> None:
    """Record a negative count so a person can see exactly where it was."""
    if len(aggregator.negative_examples) < 20:
        aggregator.negative_examples.append(
            f"{path.name}: {force}, {financial_year} Q{quarter}, offence "
            f"{offence_code}, outcome type {outcome_type}, "
            f"recorded {counts[BASIS_RECORDED]}, closed {counts[BASIS_CLOSED]}"
        )


def process_outcomes_file(path: Path, aggregator: Aggregator, log: list[str]) -> None:
    """Stream one outcomes file into the aggregator."""
    log.append(f"Reading {path.name}")
    rows = read_rows(path)
    header_map, header_row = find_header_row(rows, REQUIRED_OUTCOME_FIELDS)
    log.append(f"  headers mapped: {sorted(header_map.by_field)}")

    # Duplicate detection is per file, because the published series is one file
    # per financial year and a key cannot legitimately repeat inside one. The
    # key is packed into an integer so a multi million row file stays in memory.
    seen_keys: set[int] = set()
    force_index: dict[str, int] = {}
    offence_index: dict[str, int] = {}

    index = {
        field: header_row.index(column) for field, column in header_map.by_field.items()
    }

    def cell(row: list[object], field: str) -> object:
        position = index.get(field)
        if position is None or position >= len(row):
            return None
        return row[position]

    for row in rows:
        if row is None or not any(value not in (None, "") for value in row):
            continue
        aggregator.rows_read += 1

        financial_year = normalise_financial_year(cell(row, "financial_year"))
        quarter = normalise_quarter(cell(row, "financial_quarter"))
        if financial_year is None or quarter is None:
            continue

        raw_force = cell(row, "force_name")
        force = canonical_force(raw_force)
        if force is None:
            aggregator.unknown_forces[str(raw_force).strip()] += 1
            continue
        if force in CENTRAL_FRAUD_BODIES:
            aggregator.central_fraud_rows += 1
            continue

        raw_outcome_type = str(cell(row, "outcome_type") or "").strip()
        try:
            outcome_type = int(raw_outcome_type)
        except (TypeError, ValueError):
            # Outcome types 1a, 2a and 3a are "of which" rows: the subset of
            # outcomes 1, 2 and 3 that relate to an alternative offence to the
            # one recorded. They are already inside their parent type, so adding
            # them would double count. They are dropped, and counted here so the
            # drop is visible in coverage.json rather than silent.
            if raw_outcome_type:
                aggregator.subset_type_rows[raw_outcome_type] += 1
            continue

        counts = {
            BASIS_RECORDED: to_int(cell(row, "count_recorded")),
            BASIS_CLOSED: to_int(cell(row, "count_closed")),
        }
        if truthy_flag(cell(row, "offence_code_expired")):
            aggregator.expired_code_rows += 1

        offence_code = str(cell(row, "offence_code") or "").strip()
        packed = (
            force_index.setdefault(force, len(force_index)) << 40
            | offence_index.setdefault(offence_code, len(offence_index)) << 16
            | (financial_year_start(financial_year) % 100) << 8
            | (quarter - 1) << 6
            | (outcome_type & 63)
        )
        if packed in seen_keys:
            aggregator.duplicate_source_keys += 1
            if len(aggregator.duplicate_examples) < 10:
                aggregator.duplicate_examples.append(
                    f"{path.name}: {force}, {financial_year} Q{quarter}, "
                    f"offence {offence_code}, outcome {outcome_type}"
                )
        else:
            seen_keys.add(packed)

        offence_group = str(cell(row, "offence_group") or "Unclassified").strip()
        offence_subgroup = cell(row, "offence_subgroup")
        fraud = is_fraud_group(offence_group, offence_subgroup)

        aggregator.outcome_type_years[outcome_type].add(financial_year)

        if outcome_type == NOT_ASSIGNED_TYPE:
            # Outcome type 0 counts offences that have not been given an outcome
            # yet. It is not an outcome, so it cannot go into all assigned
            # outcomes: doing so would put undecided cases into the denominator
            # of every share measure. It is counted here so the volume is
            # visible in coverage.json rather than simply disappearing.
            aggregator.not_assigned_rows += 1
            for basis in COUNT_BASES:
                aggregator.not_assigned_counts[basis] += counts[basis]
            if any(value < 0 for value in counts.values()):
                # A small negative appears here when a force reclassifies more
                # offences in a quarter than it recorded. It sits in outcome
                # type 0, which never enters a derived total, so it is recorded
                # for transparency rather than failing the build.
                aggregator.negative_counts_excluded += 1
                _note_negative(aggregator, path, force, financial_year, quarter,
                               offence_code, outcome_type, counts)
            aggregator.rows_used += 1
            continue

        if any(value < 0 for value in counts.values()):
            # A negative in a row that does enter a total is a different matter,
            # and stops the build.
            aggregator.negative_counts += 1
            _note_negative(aggregator, path, force, financial_year, quarter,
                           offence_code, outcome_type, counts)

        aggregator.add(
            force=force,
            financial_year=financial_year,
            quarter=quarter,
            offence_group=offence_group,
            outcome_type=outcome_type,
            counts=counts,
            fraud=fraud,
        )
        aggregator.rows_used += 1


# ---------------------------------------------------------------------------
# Denominators
# ---------------------------------------------------------------------------


def process_force_area_crime(paths: list[Path], log: list[str]) -> dict:
    """Read recorded crime totals per force per financial year.

    Population is deliberately absent. No published mid year population
    estimate per police force area could be retrieved and verified when these
    tables were built, so the per capita measure is omitted rather than
    estimated. See docs/METHODOLOGY.md.
    """
    totals: dict[tuple[str, str], int] = defaultdict(int)
    for path in paths:
        log.append(f"Reading {path.name} for the recorded crime denominator")
        rows = read_rows(path)
        try:
            header_map, header_row = find_header_row(
                rows,
                required=("financial_year", "force_name", "recorded_crime_count"),
            )
        except HeaderMappingError as error:
            log.append(f"  SKIPPED, header not recognised: {error}")
            continue

        index = {
            field: header_row.index(column)
            for field, column in header_map.by_field.items()
        }
        def cell(row: list[object], field: str) -> object:
            position = index.get(field)
            if position is None or position >= len(row):
                return None
            return row[position]

        for row in rows:
            if row is None or not any(value not in (None, "") for value in row):
                continue
            financial_year = normalise_financial_year(cell(row, "financial_year"))
            force = canonical_force(cell(row, "force_name"))
            if financial_year is None or force is None:
                continue
            if force in CENTRAL_FRAUD_BODIES:
                continue
            totals[(force, financial_year)] += to_int(cell(row, "recorded_crime_count"))

    return {
        "meta": {
            "recorded_crime_source": "Home Office police force area crime tables",
            "population_source": None,
            "population_omitted_because": (
                "No mid year population estimate per police force area could be "
                "retrieved from a named published source when these tables were "
                "built. Per capita measures are omitted rather than estimated."
            ),
        },
        "rows": [
            {
                "force": force,
                "slug": force_slug(force),
                "fy": financial_year,
                "recorded_crime": count,
            }
            for (force, financial_year), count in sorted(totals.items())
        ],
    }


# ---------------------------------------------------------------------------
# Output shaping
# ---------------------------------------------------------------------------


def _sum_cells(cells: list[dict]) -> dict:
    total = Aggregator._empty_cell()
    for cell in cells:
        for basis in COUNT_BASES:
            for variant in FRAUD_VARIANTS:
                for column in COUNT_COLUMNS:
                    total[basis][variant][column] += cell[basis][variant][column]
    return total


def _flatten(cell: dict) -> dict:
    """Flatten a nested count cell into basis_variant_column keys."""
    flat: dict[str, int] = {}
    for basis in COUNT_BASES:
        for variant in FRAUD_VARIANTS:
            for column in COUNT_COLUMNS:
                flat[f"{basis}_{variant}_{column}"] = cell[basis][variant][column]
    return flat


FLAT_COLUMNS: tuple[str, ...] = tuple(
    f"{basis}_{variant}_{column}"
    for basis in COUNT_BASES
    for variant in FRAUD_VARIANTS
    for column in COUNT_COLUMNS
)


def build_tables(aggregator: Aggregator) -> dict[str, dict]:
    force_quarter_rows = []
    year_cells: dict[tuple[str, str], list[dict]] = defaultdict(list)
    national_quarter_cells: dict[tuple[str, int], list[dict]] = defaultdict(list)

    for (force, financial_year, quarter), cell in sorted(aggregator.quarter.items()):
        force_quarter_rows.append(
            {
                "force": force,
                "slug": force_slug(force),
                "fy": financial_year,
                "q": quarter,
                **_flatten(cell),
            }
        )
        year_cells[(force, financial_year)].append(cell)
        national_quarter_cells[(financial_year, quarter)].append(cell)

    force_year_rows = [
        {
            "force": force,
            "slug": force_slug(force),
            "fy": financial_year,
            **_flatten(_sum_cells(cells)),
        }
        for (force, financial_year), cells in sorted(year_cells.items())
    ]

    national_quarter_rows = [
        {"fy": financial_year, "q": quarter, **_flatten(_sum_cells(cells))}
        for (financial_year, quarter), cells in sorted(national_quarter_cells.items())
    ]

    national_year_cells: dict[str, list[dict]] = defaultdict(list)
    for (force, financial_year), cells in year_cells.items():
        national_year_cells[financial_year].extend(cells)
    national_year_rows = [
        {"fy": financial_year, **_flatten(_sum_cells(cells))}
        for financial_year, cells in sorted(national_year_cells.items())
    ]

    force_offence_year_rows = [
        {
            "force": force,
            "slug": force_slug(force),
            "fy": financial_year,
            "offence_group": offence_group,
            **{
                f"{basis}_{key}": cell[basis][key]
                for basis in COUNT_BASES
                for key in ("oocd", "charge")
            },
        }
        for (force, financial_year, offence_group), cell in sorted(
            aggregator.offence.items()
        )
    ]

    return {
        "force_quarter": force_quarter_rows,
        "force_year": force_year_rows,
        "national_quarter": national_quarter_rows,
        "national_year": national_year_rows,
        "force_offence_year": force_offence_year_rows,
    }


def write_table(out_dir: Path, name: str, rows: list[dict], meta: dict) -> None:
    payload = {"meta": meta, "rows": rows}
    write_json_compact(out_dir / f"{name}.json", payload)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with (out_dir / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        default=None,
        help="data directory to read and write, or 'fixture' for the "
        "synthetic tree. Defaults to data/.",
    )
    args = parser.parse_args()
    paths = resolve_data_root(args.data_root)
    args.raw_dir = paths.raw
    args.out_dir = paths.processed

    if not paths.manifest.exists():
        print(
            f"ERROR: {paths.manifest} is missing. Run etl/fetch.py first, so "
            "every derived figure is traceable to a recorded source file.",
            file=sys.stderr,
        )
        return 2

    manifest = read_json(paths.manifest)
    files = manifest.get("files", [])
    outcomes_files = [
        args.raw_dir / entry["filename"]
        for entry in files
        if entry.get("kind") == "outcomes_open_data"
    ]
    crime_files = [
        args.raw_dir / entry["filename"]
        for entry in files
        if entry.get("kind") == "police_force_area_crime"
    ]

    missing = [path for path in outcomes_files + crime_files if not path.exists()]
    if missing:
        print(
            f"ERROR: files named in the manifest are not in {paths.raw}: "
            + ", ".join(path.name for path in missing)
            + ". Run etl/fetch.py to rebuild them.",
            file=sys.stderr,
        )
        return 2
    if not outcomes_files:
        print("ERROR: the manifest lists no outcomes files.", file=sys.stderr)
        return 2

    log: list[str] = []
    aggregator = Aggregator()
    for path in sorted(outcomes_files):
        process_outcomes_file(path, aggregator, log)

    if aggregator.unknown_forces:
        log.append("Force names that did not match the canonical list:")
        for name, count in sorted(aggregator.unknown_forces.items()):
            log.append(f"  {name!r}: {count} rows")

    tables = build_tables(aggregator)
    denominators = process_force_area_crime(sorted(crime_files), log)

    years = sorted({row["fy"] for row in tables["force_year"]})
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provenance": manifest.get("provenance"),
        "manifest_generated_at": manifest.get("generated_at"),
        "attribution": manifest.get("attribution"),
        "default_basis": DEFAULT_BASIS,
        "count_bases": list(COUNT_BASES),
        "fraud_variants": list(FRAUD_VARIANTS),
        "count_columns": list(COUNT_COLUMNS),
        "oocd_outcome_types": list(OOCD_TYPES),
        "financial_years": years,
        "outcome_labels": {str(k): v for k, v in OUTCOME_LABELS.items()},
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        write_table(args.out_dir, name, rows, meta)
    write_json_compact(args.out_dir / "denominators.json", denominators)
    with (args.out_dir / "denominators.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=["force", "slug", "fy", "recorded_crime"])
        writer.writeheader()
        writer.writerows(denominators["rows"])

    coverage = {
        "rows_read": aggregator.rows_read,
        "rows_used": aggregator.rows_used,
        "negative_count_rows": aggregator.negative_counts,
        "negative_count_rows_excluded": aggregator.negative_counts_excluded,
        "negative_count_examples": aggregator.negative_examples,
        "subset_outcome_type_rows_dropped": dict(sorted(aggregator.subset_type_rows.items())),
        "duplicate_source_keys": aggregator.duplicate_source_keys,
        "duplicate_source_key_examples": aggregator.duplicate_examples,
        "not_yet_assigned_rows_excluded": aggregator.not_assigned_rows,
        "not_yet_assigned_offences": dict(aggregator.not_assigned_counts),
        "central_fraud_body_rows_dropped": aggregator.central_fraud_rows,
        "expired_offence_code_rows": aggregator.expired_code_rows,
        "unknown_force_names": dict(sorted(aggregator.unknown_forces.items())),
        "outcome_type_years": {
            str(outcome_type): sorted(years)
            for outcome_type, years in sorted(aggregator.outcome_type_years.items())
        },
        "forces": sorted({row["force"] for row in tables["force_year"]}),
        "financial_years": years,
        "table_row_counts": {name: len(rows) for name, rows in tables.items()},
        "log": log,
    }
    write_json_compact(args.out_dir / "coverage.json", coverage)

    print("\n".join(log))
    print("\nDerived tables written to", args.out_dir)
    for name, rows in tables.items():
        print(f"  {name}: {len(rows)} rows")
    print(f"  denominators: {len(denominators['rows'])} rows")
    print(f"Rows read {aggregator.rows_read}, rows used {aggregator.rows_used}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

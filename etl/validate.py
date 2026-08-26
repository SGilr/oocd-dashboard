#!/usr/bin/env python3
"""Check the derived tables, and stop the build when they are wrong.

A failed check exits non zero. A flagged check is written to the report for a
person to read but does not stop the build, because some of what it catches is
a real change in the world rather than a bug.

Usage:
    python etl/validate.py
    python etl/validate.py --check-urls   also resolve every annotation source
    python etl/validate.py --report data/validation-report.json
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    ANNOTATIONS_PATH,
    CANONICAL_FORCES,
    COUNT_BASES,
    ESSENTIAL_TYPES,
    NOT_ASSIGNED_TYPE,
    OOCD_TYPES,
    OUTCOME_LABELS,
    POSITIVE_TYPES,
    REPO_ROOT,
    canonical_force,
    financial_year_start,
    read_json,
    resolve_data_root,
    write_json,
)

RECONCILIATION_PATH = REPO_ROOT / "etl" / "reconciliation.yml"

# A force series that moves by more than this in one year is flagged for a
# person to look at. It is not an error: outcome 22 becoming compulsory moved
# some forces by far more than this, correctly.
YEAR_ON_YEAR_FLAG_PCT = 40.0

# Series smaller than this are ignored by the year on year check, because a
# move from 3 to 6 is a 100 per cent change and means nothing.
YEAR_ON_YEAR_MIN_BASE = 100

FRAUD_VARIANTS = ("all", "ex_fraud")


class Report:
    def __init__(self) -> None:
        self.failures: list[dict] = []
        self.flags: list[dict] = []
        self.notes: list[dict] = []

    def fail(self, check: str, detail: str, **extra) -> None:
        self.failures.append({"check": check, "detail": detail, **extra})

    def flag(self, check: str, detail: str, **extra) -> None:
        self.flags.append({"check": check, "detail": detail, **extra})

    def note(self, check: str, detail: str, **extra) -> None:
        self.notes.append({"check": check, "detail": detail, **extra})


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_forces(coverage: dict, report: Report) -> None:
    present = set(coverage.get("forces", []))
    expected = set(CANONICAL_FORCES)

    missing = sorted(expected - present)
    if missing:
        report.fail(
            "force_coverage",
            f"{len(missing)} of the 44 expected forces are absent from the "
            "derived tables",
            missing=missing,
        )

    unexpected = sorted(present - expected)
    if unexpected:
        report.fail(
            "force_coverage",
            "Forces are present that are not on the canonical list",
            unexpected=unexpected,
        )

    unknown = coverage.get("unknown_force_names", {})
    if unknown:
        report.fail(
            "force_names",
            "Force names in the source files did not match the canonical list "
            "and their rows were dropped. Add each to FORCE_ALIASES in "
            "etl/common.py, or confirm it is not a police force.",
            names=unknown,
        )

    report.note(
        "force_coverage",
        f"{len(present)} forces present, {len(expected)} expected",
    )


def check_outcome_type_coverage(coverage: dict, report: Report) -> None:
    seen = coverage.get("outcome_type_years", {})
    missing = [
        outcome_type
        for outcome_type in sorted(OUTCOME_LABELS)
        if not seen.get(str(outcome_type))
    ]

    # A missing type the classification depends on means a column was misread,
    # and the build must stop. A missing type it does not depend on can be
    # genuine: the year ending March 2026 file carries no type 19 at all, so
    # failing on that would mean the build could never pass.
    essential_missing = [t for t in missing if t in ESSENTIAL_TYPES]
    optional_missing = [t for t in missing if t not in ESSENTIAL_TYPES]

    if essential_missing:
        report.fail(
            "outcome_type_coverage",
            "Outcome types the classification depends on appear in no financial "
            "year at all, which usually means a column was misread",
            missing=[f"{t} {OUTCOME_LABELS[t]}" for t in essential_missing],
        )
    if optional_missing:
        report.flag(
            "outcome_type_coverage",
            "Outcome types appear in no financial year. This can be correct, "
            "the published tables do not carry every type in every year, but "
            "check it against the user guide before publishing.",
            missing=[f"{t} {OUTCOME_LABELS[t]}" for t in optional_missing],
        )
    if not missing:
        report.note(
            "outcome_type_coverage",
            f"All {len(OUTCOME_LABELS)} outcome types appear in at least one year",
        )

    excluded = coverage.get("not_yet_assigned_rows_excluded")
    if excluded:
        counts = coverage.get("not_yet_assigned_offences", {})
        report.note(
            "outcome_type_coverage",
            f"Outcome type {NOT_ASSIGNED_TYPE}, not yet assigned an outcome, "
            f"excluded from every total: {excluded:,} source rows, "
            f"{counts.get('closed', 0):,} on the closed basis and "
            f"{counts.get('recorded', 0):,} on the recorded basis.",
        )

    for outcome_type in OOCD_TYPES:
        years = seen.get(str(outcome_type), [])
        if years:
            report.note(
                "outcome_type_years",
                f"Outcome {outcome_type}, {OUTCOME_LABELS[outcome_type]}: "
                f"{years[0]} to {years[-1]}",
            )


def check_data_not_provided(coverage: dict, report: Report) -> None:
    """Report force years where a count was missing rather than zero."""
    affected = coverage.get("data_not_provided", {})
    if not affected:
        report.note("data_not_provided", "Every force supplied every count")
        return

    by_force: dict[str, list[str]] = {}
    for key, count in affected.items():
        force, financial_year = key.split("|")
        by_force.setdefault(force, []).append(financial_year)

    for force, years in sorted(by_force.items()):
        report.flag(
            "data_not_provided",
            f"{force} did not supply counts for {', '.join(sorted(years))}. "
            "Those rows read as zero, so the force is understated in those "
            "years and must not be compared with others across them.",
            force=force,
            financial_years=sorted(years),
            rows=sum(count for key, count in affected.items() if key.startswith(f"{force}|")),
        )


def check_negative_counts(coverage: dict, tables: dict, report: Report) -> None:
    """Negative counts are published corrections, and are carried faithfully.

    A force that cancels or reclassifies a crime recorded in an earlier quarter
    produces a negative adjustment, and the Home Office publishes it as such.
    Refusing them would mean refusing the data, and rewriting them to zero would
    be worse, because the published totals would then no longer reconcile.

    So they are carried, reported by force and year, and gated on where they
    land. A negative in a quarterly cell is a correction absorbed within its
    year. A negative in an annual total would mean corrections exceeding a whole
    year of activity, which is not a correction any more, and stops the build.
    """
    excluded = coverage.get("negative_count_rows_excluded", 0)
    if excluded:
        report.note(
            "negative_counts",
            f"{excluded:,} source rows carried a negative count in outcome type "
            f"{NOT_ASSIGNED_TYPE}, which never enters a derived total.",
            examples=coverage.get("negative_count_excluded_examples", [])[:5],
        )

    feeding = coverage.get("negative_count_rows", 0)
    if feeding:
        by_key = coverage.get("negative_counts_by_force_year", {})
        forces = sorted({key.split("|")[0] for key in by_key})
        report.flag(
            "negative_counts",
            f"{feeding:,} source rows that feed a derived total carried a "
            f"negative count, across {len(forces)} forces. These are published "
            "corrections, where a force cancelled or reclassified a crime "
            "recorded earlier, and they are carried through as published.",
            forces=forces,
            examples=coverage.get("negative_count_examples", [])[:5],
        )

    for name in ("force_year", "national_year"):
        table = tables.get(name)
        if not table:
            continue
        for row in table["rows"]:
            for key, value in row.items():
                if isinstance(value, int) and value < 0:
                    report.fail(
                        "negative_counts",
                        f"{name} has a negative annual total in {key}. "
                        "Corrections exceeding a whole year of activity are not "
                        "corrections, and cannot be published as a count.",
                        row={k: row[k] for k in ("force", "fy") if k in row},
                    )
                    return

    negative_cells = 0
    for name in ("force_quarter", "national_quarter"):
        table = tables.get(name)
        if not table:
            continue
        for row in table["rows"]:
            negative_cells += sum(
                1 for value in row.values() if isinstance(value, int) and value < 0
            )
    if negative_cells:
        report.flag(
            "negative_counts",
            f"{negative_cells} quarterly cells are negative, where a correction "
            "in that quarter exceeded the activity in it. Every annual total is "
            "non negative.",
        )
    elif not feeding and not excluded:
        report.note("negative_counts", "No negative counts anywhere")


def check_duplicate_keys(coverage: dict, tables: dict, report: Report) -> None:
    raw_duplicates = coverage.get("duplicate_source_keys", 0)
    if raw_duplicates:
        report.fail(
            "duplicate_keys",
            f"{raw_duplicates} source rows repeated a key of force, financial "
            "year, quarter, offence code and outcome type. Counts for those "
            "keys would be double counted.",
        )

    key_fields = {
        "force_quarter": ("force", "fy", "q"),
        "force_year": ("force", "fy"),
        "national_quarter": ("fy", "q"),
        "national_year": ("fy",),
        "force_offence_year": ("force", "fy", "offence_group"),
    }
    for name, fields in key_fields.items():
        table = tables.get(name)
        if not table:
            continue
        seen: set[tuple] = set()
        for row in table["rows"]:
            key = tuple(row[field] for field in fields)
            if key in seen:
                report.fail(
                    "duplicate_keys",
                    f"{name} has more than one row for {dict(zip(fields, key))}",
                )
                break
            seen.add(key)
    report.note("duplicate_keys", "Derived tables checked for repeated keys")


def check_totals_reconcile(tables: dict, report: Report) -> None:
    """The stored out of court total must equal the sum of its six components."""
    component_keys = [f"t{outcome_type}" for outcome_type in OOCD_TYPES]
    positive_keys = [f"t{outcome_type}" for outcome_type in POSITIVE_TYPES]
    checked = 0
    # Removing rows can only raise a total when some of those rows were
    # negative. That happens where a fraud correction lands, so it is a property
    # of the published data rather than an error. Collected and reported.
    larger_excluding_fraud: list[dict] = []
    for name in ("force_quarter", "force_year", "national_quarter", "national_year"):
        table = tables.get(name)
        if not table:
            continue
        for row in table["rows"]:
            for basis in COUNT_BASES:
                for variant in FRAUD_VARIANTS:
                    prefix = f"{basis}_{variant}_"
                    oocd = row[f"{prefix}oocd"]
                    component_sum = sum(row[prefix + key] for key in component_keys)
                    if oocd != component_sum:
                        report.fail(
                            "totals_reconcile",
                            f"{name}: the out of court total {oocd} does not "
                            f"equal the sum of its six components "
                            f"{component_sum}",
                            row={k: row[k] for k in ("force", "fy") if k in row},
                            basis=basis,
                            fraud_variant=variant,
                        )
                        return
                    positive = row[f"{prefix}positive"]
                    positive_sum = sum(row[prefix + key] for key in positive_keys)
                    if positive != positive_sum:
                        report.fail(
                            "totals_reconcile",
                            f"{name}: the positive outcome total {positive} does "
                            f"not equal charge plus the six out of court types "
                            f"{positive_sum}",
                            basis=basis,
                            fraud_variant=variant,
                        )
                        return
                    if positive > row[f"{prefix}assigned"]:
                        report.fail(
                            "totals_reconcile",
                            f"{name}: positive outcomes exceed all assigned "
                            "outcomes, so the denominator is wrong",
                            basis=basis,
                            fraud_variant=variant,
                        )
                        return
                    if row[f"{prefix}oocd"] > row[f"{prefix}positive"]:
                        report.fail(
                            "totals_reconcile",
                            f"{name}: out of court outcomes exceed positive "
                            "outcomes",
                        )
                        return
                    if variant == "ex_fraud" and row[f"{prefix}assigned"] > row[
                        f"{basis}_all_assigned"
                    ]:
                        larger_excluding_fraud.append(
                            {
                                "table": name,
                                "basis": basis,
                                **{k: row[k] for k in ("force", "fy", "q") if k in row},
                                "fraud_contribution": row[f"{basis}_all_assigned"]
                                - row[f"{prefix}assigned"],
                            }
                        )
                    checked += 1
    if larger_excluding_fraud:
        worst = min(entry["fraud_contribution"] for entry in larger_excluding_fraud)
        report.flag(
            "totals_reconcile",
            f"{len(larger_excluding_fraud)} cells hold a larger total with fraud "
            "excluded than with it included, because the fraud rows in them are "
            f"negative corrections. The largest negative contribution is {worst}.",
            examples=larger_excluding_fraud[:5],
        )
    report.note("totals_reconcile", f"{checked} derived totals reconciled")


def check_year_on_year(tables: dict, report: Report) -> None:
    """Flag large moves in a force series, for a person to look at."""
    table = tables.get("force_year")
    if not table:
        return
    by_force: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in table["rows"]:
        by_force[row["force"]][row["fy"]] = row

    flagged = 0
    for force, years in sorted(by_force.items()):
        ordered = sorted(years, key=financial_year_start)
        for previous_year, current_year in zip(ordered, ordered[1:]):
            previous = years[previous_year]["closed_all_oocd"]
            current = years[current_year]["closed_all_oocd"]
            if previous < YEAR_ON_YEAR_MIN_BASE:
                continue
            change = (current - previous) / previous * 100
            if abs(change) > YEAR_ON_YEAR_FLAG_PCT:
                flagged += 1
                report.flag(
                    "year_on_year",
                    f"{force} out of court disposals moved {change:+.1f} per "
                    f"cent from {previous_year} to {current_year}, "
                    f"{previous} to {current}. Check whether an annotation "
                    "explains it before publishing.",
                    force=force,
                    from_year=previous_year,
                    to_year=current_year,
                    change_pct=round(change, 1),
                )
    report.note(
        "year_on_year",
        f"{flagged} force year movements above {YEAR_ON_YEAR_FLAG_PCT} per cent "
        "flagged for review",
    )


def check_annotations(report: Report, check_urls: bool) -> None:
    with ANNOTATIONS_PATH.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)

    annotations = document.get("annotations", [])
    if not annotations:
        report.fail("annotations", "etl/annotations.yml lists no annotations")
        return

    seen_ids: set[str] = set()
    for annotation in annotations:
        annotation_id = annotation.get("id")
        if not annotation_id:
            report.fail("annotations", "An annotation has no id")
            continue
        if annotation_id in seen_ids:
            report.fail("annotations", f"Duplicate annotation id: {annotation_id}")
        seen_ids.add(annotation_id)

        for field in ("scope", "financial_years", "label", "text", "source_url"):
            if not annotation.get(field):
                report.fail(
                    "annotations", f"{annotation_id} is missing {field}"
                )

        scope = annotation.get("scope")
        if isinstance(scope, list):
            for name in scope:
                if canonical_force(name) is None:
                    report.fail(
                        "annotations",
                        f"{annotation_id} is scoped to '{name}', which is not a "
                        "canonical force name",
                    )
        elif scope != "national":
            report.fail(
                "annotations",
                f"{annotation_id} has scope '{scope}', expected 'national' or a "
                "list of force names",
            )

        if annotation.get("needs_review"):
            report.flag(
                "annotations",
                f"{annotation_id} is marked needs_review: it makes a claim that "
                "has not been reconciled with the data or with a named source. "
                "Settle it before publishing.",
                label=annotation.get("label"),
            )

        verified = annotation.get("source_url_verified")
        if verified is False:
            report.fail(
                "annotations",
                f"{annotation_id} has a source URL that did not resolve. Find "
                "the correct source rather than substituting another.",
                source_url=annotation.get("source_url"),
            )
        elif verified is None:
            report.flag(
                "annotations",
                f"{annotation_id} has an unverified source URL. Run "
                "validate.py --check-urls somewhere with network access to the "
                "sources before publishing.",
                source_url=annotation.get("source_url"),
            )

    if check_urls:
        _resolve_annotation_urls(document, report)

    report.note("annotations", f"{len(annotations)} annotations checked")


def _write_back_verification(document: dict) -> None:
    """Update only the source_url_verified lines, leaving the file otherwise as
    it was.

    Dumping the parsed document back would strip every comment in the file,
    including the header that explains what each field is for. This edits the
    one line per annotation that changed and touches nothing else.
    """
    lines = ANNOTATIONS_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    states = {
        annotation["id"]: annotation.get("source_url_verified")
        for annotation in document.get("annotations", [])
    }

    current: str | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("- id:"):
            current = stripped.split(":", 1)[1].strip()
        elif current and stripped.startswith("source_url_verified:"):
            value = states.get(current)
            rendered = "null" if value is None else ("true" if value else "false")
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = f"{indent}source_url_verified: {rendered}\n"
            current = None

    ANNOTATIONS_PATH.write_text("".join(lines), encoding="utf-8")


def _resolve_annotation_urls(document: dict, report: Report) -> None:
    """Resolve every annotation source URL and write the result back.

    Only evidence that a page is gone marks a source false. Everything else
    that is not a clean answer stays unknown, because a check that cannot tell
    "this source has moved" from "something refused me" is worse than no check.

      2xx or 3xx            true, the source is there
      404 or 410            false, the source has gone, and the build fails
      403, 429, 5xx         unknown, we were refused or the server faltered.
                            Many public sites answer 403 to a script and 200 to
                            a browser, so this needs a person to look.
      no response at all    unknown, the network is blocked or down
    """
    GONE = {404, 410}
    import requests

    session = requests.Session()
    session.headers.update(
        {"User-Agent": "oocd-dashboard/1.0 annotation source check"}
    )
    unreachable = 0
    for annotation in document.get("annotations", []):
        url = annotation.get("source_url")
        if not url:
            continue
        try:
            response = session.head(url, allow_redirects=True, timeout=30)
            if response.status_code >= 400:
                response = session.get(url, timeout=30, stream=True)
            status = response.status_code
        except Exception as error:  # noqa: BLE001
            unreachable += 1
            if annotation.get("source_url_verified") is not True:
                annotation["source_url_verified"] = None
            report.flag(
                "annotation_urls",
                f"{annotation['id']}: could not reach {url}. This is a network "
                f"problem, not a bad source, so it stays unverified rather than "
                f"being marked broken. {type(error).__name__}",
            )
            continue

        if status < 400:
            annotation["source_url_verified"] = True
            report.note(
                "annotation_urls", f"{annotation['id']}: resolved, {status}. {url}"
            )
        elif status in GONE:
            annotation["source_url_verified"] = False
            report.fail(
                "annotation_urls",
                f"{annotation['id']}: the source URL returned {status}, so the "
                "source has gone. Find the correct source rather than "
                "substituting another.",
                source_url=url,
            )
        else:
            unreachable += 1
            # An inconclusive answer never overwrites a confirmation somebody
            # already made. British Transport Police answers 403 to a script
            # and 200 to a browser, and a person has checked it.
            already = annotation.get("source_url_verified") is True
            if not already:
                annotation["source_url_verified"] = None
            report.flag(
                "annotation_urls",
                f"{annotation['id']}: the source URL returned {status}, which is "
                "a refusal or a server fault rather than proof the page has "
                + (
                    "gone. It stays verified, because a person has already "
                    f"confirmed it in a browser. {url}"
                    if already
                    else f"gone. Open it in a browser and confirm it loads. {url}"
                ),
            )

    _write_back_verification(document)

    if unreachable:
        report.flag(
            "annotation_urls",
            f"{unreachable} source URLs could not be reached from this machine. "
            "Run this again from somewhere with access to gov.uk before "
            "publishing.",
        )


def check_reconciliation(tables: dict, manifest: dict, report: Report) -> None:
    """Compare derived national totals with figures typed from a bulletin."""
    with RECONCILIATION_PATH.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle) or {}
    targets = document.get("targets") or []

    published = [t for t in targets if t.get("kind", "published") == "published"]
    if not published:
        message = (
            "etl/reconciliation.yml records no target of kind 'published'. Only "
            "a figure read from a Home Office bulletin can catch a misreading "
            "of what the data means, because a recomputation from the same "
            "source shares any misunderstanding with the extract. Add one "
            "before publishing."
        )
        if manifest.get("provenance") == "home_office_open_data":
            report.fail("reconciliation", message)
        else:
            report.flag("reconciliation", message + " Provenance is not live data.")

    if not targets:
        return

    if manifest.get("provenance") != "home_office_open_data":
        # The targets describe the published figures. Comparing them with
        # invented numbers would fail every fixture build for no useful reason.
        report.note(
            "reconciliation",
            f"{len(targets)} reconciliation targets not compared: this build "
            f"carries provenance {manifest.get('provenance')!r} rather than the "
            "published files.",
        )
        return

    national = {row["fy"]: row for row in tables["national_year"]["rows"]}
    measure_keys = {
        "oocd_total": "oocd",
        "outcome_types": None,
        "charge_total": "t1",
        "assigned_total": "assigned",
        "positive_total": "positive",
    }

    for target in targets:
        financial_year = target["financial_year"]
        row = national.get(financial_year)
        if row is None:
            report.fail(
                "reconciliation",
                f"{target['id']}: the derived tables hold no national row for "
                f"{financial_year}",
            )
            continue
        basis = target.get("basis", "closed")
        variant = target.get("fraud_variant", "all")
        outcome_types = target.get("outcome_types")
        if outcome_types:
            # A target can name the outcome types it covers, so a published
            # figure that groups them differently from this dashboard can still
            # be compared. Table 3.1 of the bulletin, for instance, counts out
            # of court as types 2, 3, 6, 7 and 8, with outcome 22 reported
            # separately.
            column = f"{basis}_{variant}_types_{'_'.join(str(t) for t in outcome_types)}"
            derived = sum(row[f"{basis}_{variant}_t{t}"] for t in outcome_types)
        else:
            column = f"{basis}_{variant}_{measure_keys[target['measure']]}"
            derived = row[column]
        published = target["value"]
        # 'published' here is the target value, whatever its kind.
        tolerance = target.get("tolerance_pct", 0.5)
        difference_pct = (
            abs(derived - published) / published * 100 if published else 100.0
        )
        entry = {
            "id": target["id"],
            "kind": target.get("kind", "published"),
            "financial_year": financial_year,
            "measure": target["measure"],
            "column": column,
            "published": published,
            "derived": derived,
            "difference_pct": round(difference_pct, 3),
            "tolerance_pct": tolerance,
            "citation": target.get("citation"),
            "source_url": target.get("source_url"),
        }
        if difference_pct > tolerance:
            report.fail(
                "reconciliation",
                f"{target['id']}: derived {derived} against published "
                f"{published}, {difference_pct:.2f} per cent apart, tolerance "
                f"{tolerance} per cent",
                **entry,
            )
        else:
            report.note(
                "reconciliation",
                f"{target['id']} ({entry['kind']}): derived {derived:,} against "
                f"{published:,}, {difference_pct:.2f} per cent apart",
                **entry,
            )


def check_provenance(manifest: dict, report: Report) -> None:
    provenance = manifest.get("provenance")
    if provenance == "home_office_open_data":
        report.note("provenance", "Manifest records live Home Office source files")
        return
    if provenance == "fixture":
        report.flag(
            "provenance",
            "The manifest records synthetic fixture data, not the Home Office "
            "files. The site will carry a banner saying so, and must not be "
            "published in this state.",
        )
        return
    report.fail(
        "provenance",
        f"The manifest records an unrecognised provenance: {provenance!r}",
    )


# ---------------------------------------------------------------------------


def load_tables(processed_dir: Path) -> dict:
    tables = {}
    for name in (
        "force_quarter",
        "force_year",
        "national_quarter",
        "national_year",
        "force_offence_year",
    ):
        path = processed_dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} is missing. Run etl/transform.py before validating."
            )
        tables[name] = read_json(path)
    return tables


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-urls",
        action="store_true",
        help="resolve every annotation source URL and record the result",
    )
    parser.add_argument(
        "--urls-only",
        action="store_true",
        help="check the annotation source URLs and nothing else. Needs no "
        "derived tables, so it can be run on a fresh clone before any extract.",
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help="data directory to validate, or 'fixture'. Defaults to data/.",
    )
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()
    paths = resolve_data_root(args.data_root)
    report_path = args.report or paths.root / "validation-report.json"

    report = Report()

    if args.urls_only:
        # Deliberately does not touch the derived tables: this mode exists so
        # the source URLs can be checked on a fresh clone, from a machine that
        # can reach them, without running the extract first.
        check_annotations(report, check_urls=True)
        for note in report.notes:
            print(f"  note  [{note['check']}] {note['detail']}")
        for flag in report.flags:
            print(f"  FLAG  [{flag['check']}] {flag['detail']}")
        for failure in report.failures:
            print(f"  FAIL  [{failure['check']}] {failure['detail']}")
        if report.failures:
            print(f"\n{len(report.failures)} source URLs returned an error. Find "
                  "the correct source rather than substituting another.")
            return 1
        unreachable = [f for f in report.flags if "could not reach" in f["detail"]]
        if unreachable:
            print(f"\n{len(unreachable)} source URLs could not be reached from "
                  "this machine, so they stay unverified. Nothing was marked "
                  "broken. Run this again from somewhere with access.")
            return 1
        print("\nEvery annotation source URL resolved. etl/annotations.yml updated.")
        return 0

    tables = load_tables(paths.processed)
    coverage = read_json(paths.processed / "coverage.json")
    manifest = read_json(paths.manifest)

    check_provenance(manifest, report)
    check_forces(coverage, report)
    check_outcome_type_coverage(coverage, report)
    check_negative_counts(coverage, tables, report)
    check_data_not_provided(coverage, report)
    check_duplicate_keys(coverage, tables, report)
    check_totals_reconcile(tables, report)
    check_year_on_year(tables, report)
    check_annotations(report, args.check_urls)
    check_reconciliation(tables, manifest, report)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provenance": manifest.get("provenance"),
        "row_counts": coverage.get("table_row_counts", {}),
        "financial_years": coverage.get("financial_years", []),
        "forces": len(coverage.get("forces", [])),
        "passed": not report.failures,
        "failures": report.failures,
        "flags": report.flags,
        "notes": report.notes,
    }
    write_json(report_path, payload)

    print("Validation report")
    print("=" * 60)
    print(f"Provenance: {manifest.get('provenance')}")
    print(f"Forces: {len(coverage.get('forces', []))}")
    print(f"Financial years: {', '.join(coverage.get('financial_years', []))}")
    print("Row counts:")
    for name, count in sorted(coverage.get("table_row_counts", {}).items()):
        print(f"  {name}: {count}")
    print()
    for note in report.notes:
        print(f"  note  [{note['check']}] {note['detail']}")
    for flag in report.flags:
        print(f"  FLAG  [{flag['check']}] {flag['detail']}")
    for failure in report.failures:
        print(f"  FAIL  [{failure['check']}] {failure['detail']}")
    print()
    print(f"Written to {report_path}")

    if report.failures:
        print(f"\nFAILED: {len(report.failures)} checks failed, the build stops here.")
        return 1
    print(f"\nPassed, with {len(report.flags)} items flagged for review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

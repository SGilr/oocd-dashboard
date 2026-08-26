#!/usr/bin/env python3
"""Read the Ministry of Justice weekly prison estate bulletin.

The capacity panel on /capacity shows two published figures, the prison
population and the useable operational capacity, and the headroom between
them. This script produces the small JSON file that panel reads.

The route is:

1. GET the GOV.UK Content API entry for the weekly publication. The response
   is JSON and ``details.attachments`` is an ordered list, each entry carrying
   a title such as "Population bulletin: weekly 24 August 2026" and a direct
   URL to an .ods file on assets.publishing.service.gov.uk.
2. Download the newest attachment. An .ods file is a zip archive whose
   content.xml holds the sheets, so the standard library reads it and no
   spreadsheet dependency is added to the ETL for two numbers.
3. Find the figures by matching row labels rather than cell coordinates, so a
   layout change cannot silently produce a wrong number. Only the current
   week's block of the sheet is searched, because the bulletin repeats the
   same labels for last week, for twelve months ago and again under its
   definitions.
4. Write the record only when the population and the capacity were both found,
   both sit inside a plausible range for the national estate, and the
   published headroom equals the one less the other.

On a failed match the previous record is kept, its parser_status is set to
"needs_review" and the script exits non zero. A page showing last week's
verified figure with a note is correct. A page showing a wrong figure
confidently is not.

Every run writes data/_sheet-dump.json, the flattened sheets with their names,
so a label that has moved can be corrected from the dump rather than guessed
at. The dump is gitignored and the workflow uploads it as an artifact.

The labels were confirmed against the live file for Monday 24 August 2026 on
26 August 2026. See LABELS for the layout that run revealed.

Usage:
    python etl/prison_capacity.py --dry-run   read and report, write only the dump
    python etl/prison_capacity.py             write data/processed/prison-capacity.json
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED_DIR, DATA_DIR, write_json  # noqa: E402

# The publication slug carries the calendar year and will change in January.
# When it does, this run fails at the Content API rather than quietly reading
# last year's final bulletin, which is the behaviour we want.
CONTENT_API = (
    "https://www.gov.uk/api/content/government/publications/"
    "prison-population-weekly-estate-figures-2026"
)

USER_AGENT = (
    "oocd-dashboard/1.0 (research dashboard, Oxon Advisory; "
    "contact admin@oxonadvisory.com) python-requests"
)
REQUEST_TIMEOUT_SECONDS = 120

OUT_PATH = PROCESSED_DIR / "prison-capacity.json"
DUMP_PATH = DATA_DIR / "_sheet-dump.json"

# Row labels, tried in order, first match wins.
#
# Confirmed against the live bulletin on 26 August 2026, the file for Monday
# 24 August. The sheet is called "Data" and its rows read:
#
#     0  Population and Capacity Briefing for Monday 24 August 2026
#     1                              Total       Adult Male  Female  YCS
#     2  Population                  86843       83170       3388    285
#     3  Useable Operational Capac.  88937       84835       3718    384
#     4  Headroom                     2094        1665         330     99
#     5  Home Detention Curfew        4096
#     6  Population and Capacity on previous Mondays
#     7  Last Week: 17 August 2026   Total       Adult Male  Female  YCS
#     8  Population                  86722       ...
#    ...
#    17  Definitions
#    18  Useable Operational Capac.  <definition prose>
#
# The exact labels come first. That matters: on the first live run the
# population matched on the broad fallback below, and rows 0 and 6 both
# contain the word "population". They were passed over only because neither
# has a number to the right of it, which is luck rather than design.
LABELS: dict[str, list[str]] = {
    "population": [
        r"^population$",
        r"^total\s+prison\s+population",
        r"^prison\s+population",
        r"^population\b.*\btotal",
        r"^total\s+population",
        r"\bpopulation\b",
    ],
    "capacity": [
        r"^useable\s+operational\s+capacity$",
        r"^usable\s+operational\s+capacity$",
        r"useable\s+operational\s+capacity",
        r"usable\s+operational\s+capacity",
        r"operational\s+capacity",
        r"\bcapacity\b",
    ],
    # Published in the bulletin rather than derived, so the page can say which
    # it is showing. Read and cross-checked, never used to fill a gap.
    "headroom": [
        r"^headroom$",
    ],
}

# Everything below the first of these belongs to another week or to the notes.
#
# The bulletin repeats the same three labels for last week and for twelve
# months ago, and again under "Definitions". Searching the whole sheet means
# that in a week where the current block reads "Historic data not available",
# as the twelve month block did on 24 August 2026, the search falls through to
# last week's figures and publishes them under this week's date. That is a
# confident wrong answer, so the search stops at this boundary instead and the
# run fails loudly.
CURRENT_BLOCK_END = [
    r"previous\s+mondays",
    r"^definitions$",
    r"^last\s+week\b",
    r"months?\s+ago\b",
]

# A national prison estate figure for England and Wales, not a percentage, a
# year or a single establishment.
#
# The floor matters more than it looks. The kit's reference implementation put
# it at 1,000, which admits a bare year: a table with a date in the cell beside
# its label reads 2026 as the population, passes every other check and puts a
# confident wrong number on the page. The estate has held between 80,000 and
# 90,000 for two decades, so a band of 40,000 to 150,000 is generous about
# genuine movement and closed to years, percentages, footnote markers and
# establishment level counts. A figure outside it fails the run and last
# week's verified figure stays on the page, which is the safe direction.
PLAUSIBLE_MIN = 40_000
PLAUSIBLE_MAX = 150_000

# Capacity below this multiple of the population means the two labels matched
# different things, whatever they were.
MIN_CAPACITY_RATIO = 0.8

NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
}

DATE_IN_TITLE = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")
MONTHS = {
    name.lower(): number
    for number, name in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}

# Guards against the trailing filler rows and columns an .ods carries, which
# can claim to repeat a million times.
MAX_ROW_REPEAT = 8
MAX_COLUMN_REPEAT = 64
MAX_DUMP_ROWS_PER_SHEET = 120


class BulletinError(RuntimeError):
    """The bulletin could not be reached or read at all."""


def fetch(session: requests.Session, url: str) -> bytes:
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.content


def newest_attachment(payload: dict) -> dict:
    """Return the .ods attachment whose title carries the latest date."""
    attachments = (payload.get("details") or {}).get("attachments") or []
    ods = [a for a in attachments if str(a.get("url", "")).lower().endswith(".ods")]
    if not ods:
        raise BulletinError(
            "No .ods attachments on the publication page. The Content API "
            "response changed shape, or the bulletin is now published in "
            "another format. Inspect the payload before editing this."
        )

    def sort_key(attachment: dict) -> tuple[int, int, int]:
        match = DATE_IN_TITLE.search(attachment.get("title", ""))
        if not match:
            return (0, 0, 0)
        return (
            int(match.group(3)),
            MONTHS.get(match.group(2).lower(), 0),
            int(match.group(1)),
        )

    dated = [a for a in ods if sort_key(a) != (0, 0, 0)]
    if dated:
        return max(dated, key=sort_key)
    # The publication lists newest first, so this is the fallback when no
    # title carries a parseable date.
    return ods[0]


def attachment_date(attachment: dict) -> str | None:
    match = DATE_IN_TITLE.search(attachment.get("title", ""))
    if not match:
        return None
    month = MONTHS.get(match.group(2).lower())
    if not month:
        return None
    return "%s-%02d-%02d" % (match.group(3), month, int(match.group(1)))


def cell_text(cell: ET.Element) -> str:
    """The visible text of a cell, or its office:value when it carries one."""
    value = cell.get("{%s}value" % NS["office"])
    if value is not None:
        return value
    parts = ["".join(p.itertext()) for p in cell.findall("{%s}p" % NS["text"])]
    return " ".join(part.strip() for part in parts if part).strip()


def flatten_ods(blob: bytes) -> list[tuple[str, list[list[str]]]]:
    """Return every sheet as (name, rows), repeats expanded.

    Every sheet is read, not just the first. The weekly bulletin opens on a
    cover or contents sheet, so a first sheet only reader finds no figures at
    all and reports a parse failure that is really a reader failure.
    """
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        content = archive.read("content.xml")
    tree = ET.fromstring(content)

    sheets: list[tuple[str, list[list[str]]]] = []
    for table in tree.iter("{%s}table" % NS["table"]):
        name = table.get("{%s}name" % NS["table"]) or "unnamed"
        rows: list[list[str]] = []
        for row in table.iter("{%s}table-row" % NS["table"]):
            repeat = min(
                int(row.get("{%s}number-rows-repeated" % NS["table"], "1")),
                MAX_ROW_REPEAT,
            )
            cells: list[str] = []
            for cell in row.findall("{%s}table-cell" % NS["table"]):
                columns = min(
                    int(cell.get("{%s}number-columns-repeated" % NS["table"], "1")),
                    MAX_COLUMN_REPEAT,
                )
                cells.extend([cell_text(cell)] * columns)
            while cells and cells[-1] == "":
                cells.pop()
            for _ in range(repeat):
                rows.append(list(cells))
        sheets.append((name, [row for row in rows if any(row)]))
    return sheets


def to_number(raw: str) -> int | None:
    """A plausible prison estate figure, or None."""
    if raw is None:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(raw))
    if cleaned in ("", "-", ".", "-."):
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if not PLAUSIBLE_MIN <= value <= PLAUSIBLE_MAX:
        return None
    return int(round(value))


def current_block(rows: list[list[str]]) -> list[list[str]]:
    """The rows above the first heading that starts another week or the notes."""
    boundaries = [re.compile(pattern, re.I) for pattern in CURRENT_BLOCK_END]
    for index, row in enumerate(rows):
        for cell in row:
            text = (cell or "").strip()
            if text and any(boundary.search(text) for boundary in boundaries):
                return rows[:index]
    return rows


def find_figure(
    sheets: list[tuple[str, list[list[str]]]], patterns: list[str]
) -> tuple[int | None, str | None, str | None]:
    """The first figure to the right of a cell matching one of the patterns.

    Only the current week's block of each sheet is searched, see
    CURRENT_BLOCK_END. Returns the value, the label it matched on and the
    sheet it was found in, so a wrong match can be recognised in the output
    rather than trusted.
    """
    scoped = [(name, current_block(rows)) for name, rows in sheets]
    for pattern in patterns:
        expression = re.compile(pattern, re.I)
        for sheet_name, rows in scoped:
            for row in rows:
                for index, cell in enumerate(row):
                    if not cell or not cell.strip():
                        continue
                    if not expression.search(cell.strip()):
                        continue
                    for candidate in row[index + 1:]:
                        number = to_number(candidate)
                        if number is not None:
                            return number, cell.strip(), sheet_name
    return None, None, None


def find_headroom(
    sheets: list[tuple[str, list[list[str]]]]
) -> tuple[int | None, str | None, str | None]:
    """The published headroom, which is far smaller than a national total.

    to_number's band is written for a population or a capacity and would
    reject a four figure headroom, so this reads the cell directly. It is only
    ever used as a cross-check, never to fill a gap.
    """
    scoped = [(name, current_block(rows)) for name, rows in sheets]
    expression = re.compile(LABELS["headroom"][0], re.I)
    for sheet_name, rows in scoped:
        for row in rows:
            for index, cell in enumerate(row):
                text = (cell or "").strip()
                if not text or not expression.search(text):
                    continue
                for candidate in row[index + 1:]:
                    cleaned = re.sub(r"[^0-9.\-]", "", str(candidate))
                    if cleaned in ("", "-", ".", "-."):
                        continue
                    try:
                        return int(round(float(cleaned))), text, sheet_name
                    except ValueError:
                        continue
    return None, None, None


def load_existing() -> dict:
    try:
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_dump(attachment: dict, sheets: list[tuple[str, list[list[str]]]]) -> None:
    DUMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    DUMP_PATH.write_text(
        json.dumps(
            {
                "source_title": attachment.get("title"),
                "source_url": attachment.get("url"),
                "sheet_names": [name for name, _ in sheets],
                "sheets": [
                    {"name": name, "rows": rows[:MAX_DUMP_ROWS_PER_SHEET]}
                    for name, rows in sheets
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="read the bulletin and report, writing only the sheet dump",
    )
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})

    print(f"Reading the publication: {CONTENT_API}")
    payload = json.loads(fetch(session, CONTENT_API).decode("utf-8"))
    attachment = newest_attachment(payload)

    print(f"Newest attachment: {attachment.get('title')}")
    print(f"  {attachment.get('url')}")
    blob = fetch(session, attachment["url"])
    print(f"  {len(blob):,} bytes")

    sheets = flatten_ods(blob)
    write_dump(attachment, sheets)
    print(f"\nSheets: {', '.join(name for name, _ in sheets)}")
    for name, rows in sheets:
        print(f"  {name}: {len(rows)} non-empty rows")
    print(f"Dump written to {DUMP_PATH.relative_to(DATA_DIR.parent)}")

    population, population_label, population_sheet = find_figure(
        sheets, LABELS["population"]
    )
    capacity, capacity_label, capacity_sheet = find_figure(sheets, LABELS["capacity"])
    # The bulletin publishes headroom as well, which makes it a check rather
    # than a third thing to trust: it is capacity less population by
    # definition, so if the published figure disagrees the three labels did
    # not come from the same block of the sheet.
    published_headroom, headroom_label, _ = find_headroom(sheets)

    print("\nMatched:")
    print(f"  population : {population} on {population_label!r} in {population_sheet!r}")
    print(f"  capacity   : {capacity} on {capacity_label!r} in {capacity_sheet!r}")
    print(f"  headroom   : {published_headroom} on {headroom_label!r}")

    derived_headroom = (
        capacity - population if population is not None and capacity is not None else None
    )
    headroom_disagrees = (
        published_headroom is not None
        and derived_headroom is not None
        and published_headroom != derived_headroom
    )
    if headroom_disagrees:
        print(
            f"  the published headroom {published_headroom} is not the "
            f"published capacity less the published population "
            f"({capacity} - {population} = {derived_headroom}), so the three "
            f"labels did not come from one block",
            file=sys.stderr,
        )

    incomplete = (
        population is None
        or capacity is None
        or capacity < population * MIN_CAPACITY_RATIO
        or headroom_disagrees
    )
    if incomplete:
        previous = load_existing()
        print(
            "\nPARSE INCOMPLETE. The expected labels were not matched, or the "
            "figures failed the sanity check.\n"
            "Read data/_sheet-dump.json, find the rows holding the two "
            "figures, and add their labels to LABELS in etl/prison_capacity.py.",
            file=sys.stderr,
        )
        if args.dry_run:
            return 2
        if not previous:
            print(
                "No previous record to keep. Nothing written.",
                file=sys.stderr,
            )
            return 2
        previous["parser_status"] = "needs_review"
        previous["fetched_at"] = datetime.now(timezone.utc).isoformat()
        previous["note"] = (
            "The weekly file was downloaded but the expected labels were not "
            "matched, or the figures failed the sanity check. The previous "
            "values are retained and shown on the page."
        )
        write_json(OUT_PATH, previous)
        print(f"Previous figures retained in {OUT_PATH.name}.", file=sys.stderr)
        return 2

    record = {
        "as_at": attachment_date(attachment),
        "published": payload.get("public_updated_at"),
        "population": population,
        "useable_operational_capacity": capacity,
        "headroom": published_headroom if published_headroom is not None else derived_headroom,
        # False when the bulletin published the figure itself, which it does
        # weekly. The seed record derives it from two figures of different
        # dates, and the page says which it is showing.
        "headroom_derived": published_headroom is None,
        "source_title": attachment.get("title"),
        "source_url": attachment.get("url"),
        "matched_on": {
            "population": population_label,
            "capacity": capacity_label,
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "parser_status": "ok",
        # The note has to follow headroom_derived. The bulletin publishes
        # headroom, so on the weekly path all three figures are published and
        # saying otherwise understates the provenance of one of them.
        "note": (
            "Read automatically from the Ministry of Justice weekly prison "
            "estate bulletin. Population, useable operational capacity and "
            "headroom are all published in it."
            if published_headroom is not None
            else "Read automatically from the Ministry of Justice weekly "
            "prison estate bulletin. Headroom is capacity less population, "
            "computed here rather than published."
        ),
    }

    print("\n" + json.dumps(record, indent=2))
    if args.dry_run:
        print("\nDry run. Only the sheet dump was written.")
        return 0

    write_json(OUT_PATH, record)
    print(f"\nWritten to {OUT_PATH.relative_to(DATA_DIR.parent)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BulletinError, requests.RequestException) as error:
        print(f"\nThe bulletin could not be read: {error}", file=sys.stderr)
        raise SystemExit(1)

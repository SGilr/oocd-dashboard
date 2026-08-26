#!/usr/bin/env python3
"""
Read the latest Ministry of Justice weekly prison estate bulletin and write a small
JSON file for the page to display.

Route
-----
1. GET https://www.gov.uk/api/content/government/publications/prison-population-weekly-estate-figures-2026
   The GOV.UK Content API returns JSON. details.attachments is an ordered list; each
   entry carries a title such as "Population bulletin: weekly 24 August 2026" and a
   direct url to an .ods file on assets.publishing.service.gov.uk.
2. Download the newest attachment and parse it. An .ods file is a zip archive whose
   content.xml holds the sheet, so no third party library is needed.
3. Find the population and useable operational capacity rows by matching their labels,
   not by cell coordinates, so a layout change shifts nothing.
4. Write data/prison-capacity.json only when both figures were found and look sane.

Honest caveat
-------------
The bulletin's exact row labels were not readable from the environment this script was
written in, because assets.publishing.service.gov.uk was unreachable. The label patterns
below are therefore candidates. On the first run the script writes the whole flattened
sheet to data/_sheet-dump.json and, if it cannot match both figures, sets
parser_status to "needs_review" and leaves the previous good data in place rather than
overwriting it with nulls. Open the dump, add the real label to LABELS, and the run
after that will be clean.

Usage
-----
    python3 scripts/fetch_prison_figures.py                 # writes data/prison-capacity.json
    python3 scripts/fetch_prison_figures.py --dry-run       # prints, writes nothing but the dump
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from urllib.request import Request, urlopen

CONTENT_API = (
    "https://www.gov.uk/api/content/government/publications/"
    "prison-population-weekly-estate-figures-2026"
)
UA = "oocd.howpreventionworks.com weekly figures ingest (+contact via site)"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(REPO_ROOT, "data", "prison-capacity.json")
DUMP_PATH = os.path.join(REPO_ROOT, "data", "_sheet-dump.json")

# Candidate row labels, tried in order. Add the real one after reading the dump.
LABELS = {
    "population": [
        r"^total\s+prison\s+population",
        r"^prison\s+population",
        r"^population\b.*\btotal",
        r"^total\s+population",
        r"\bpopulation\b",
    ],
    "capacity": [
        r"useable\s+operational\s+capacity",
        r"usable\s+operational\s+capacity",
        r"operational\s+capacity",
        r"\bcapacity\b",
    ],
}

NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
}

DATE_IN_TITLE = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")
MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}


def get(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(req, timeout=60) as resp:
        return resp.read()


def newest_attachment(payload: dict) -> dict:
    """Return the attachment whose title carries the latest date."""
    attachments = (payload.get("details") or {}).get("attachments") or []
    ods = [a for a in attachments if str(a.get("url", "")).lower().endswith(".ods")]
    if not ods:
        raise SystemExit("No .ods attachments found on the publication page.")

    def key(a):
        m = DATE_IN_TITLE.search(a.get("title", ""))
        if not m:
            return (0, 0, 0)
        day, month, year = m.group(1), m.group(2).lower(), m.group(3)
        return (int(year), MONTHS.get(month, 0), int(day))

    dated = [a for a in ods if key(a) != (0, 0, 0)]
    if dated:
        return max(dated, key=key)
    return ods[0]  # publication lists newest first


def attachment_date(a: dict) -> str | None:
    m = DATE_IN_TITLE.search(a.get("title", ""))
    if not m:
        return None
    month = MONTHS.get(m.group(2).lower())
    if not month:
        return None
    return "%s-%02d-%02d" % (m.group(3), month, int(m.group(1)))


def flatten_ods(blob: bytes) -> list[list[str]]:
    """Return the first sheet as a list of rows of cell strings, repeats expanded."""
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        content = z.read("content.xml")
    tree = ET.fromstring(content)

    rows_out: list[list[str]] = []
    for table in tree.iter("{%s}table" % NS["table"]):
        for row in table.iter("{%s}table-row" % NS["table"]):
            row_repeat = int(row.get("{%s}number-rows-repeated" % NS["table"], "1"))
            row_repeat = min(row_repeat, 8)  # guard against the trailing filler rows
            cells: list[str] = []
            for cell in row.findall("{%s}table-cell" % NS["table"]):
                repeat = int(cell.get("{%s}number-columns-repeated" % NS["table"], "1"))
                repeat = min(repeat, 64)
                value = cell.get("{%s}value" % NS["office"])
                if value is None:
                    parts = [
                        "".join(p.itertext())
                        for p in cell.findall("{%s}p" % NS["text"])
                    ]
                    value = " ".join(x.strip() for x in parts if x is not None).strip()
                cells.extend([value] * repeat)
            while cells and cells[-1] == "":
                cells.pop()
            for _ in range(row_repeat):
                rows_out.append(list(cells))
        break  # first sheet only
    return [r for r in rows_out if any(c for c in r)]


def to_number(raw: str) -> int | None:
    if raw is None:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(raw))
    if cleaned in ("", "-", ".", "-."):
        return None
    try:
        val = float(cleaned)
    except ValueError:
        return None
    if not (1000 <= val <= 200000):  # a prison estate figure, not a percentage or a year
        return None
    return int(round(val))


def find_figure(rows: list[list[str]], patterns: list[str]) -> tuple[int | None, str | None]:
    for pattern in patterns:
        rx = re.compile(pattern, re.I)
        for row in rows:
            for idx, cell in enumerate(row):
                if not isinstance(cell, str) or not cell.strip():
                    continue
                if rx.search(cell.strip()):
                    for candidate in row[idx + 1:]:
                        num = to_number(candidate)
                        if num is not None:
                            return num, cell.strip()
    return None, None


def load_existing() -> dict:
    try:
        with open(OUT_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    payload = json.loads(get(CONTENT_API).decode("utf-8"))
    attachment = newest_attachment(payload)
    blob = get(attachment["url"])
    rows = flatten_ods(blob)

    os.makedirs(os.path.dirname(DUMP_PATH), exist_ok=True)
    with open(DUMP_PATH, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "source_title": attachment.get("title"),
                "source_url": attachment.get("url"),
                "rows": rows[:200],
            },
            fh,
            indent=2,
        )

    population, pop_label = find_figure(rows, LABELS["population"])
    capacity, cap_label = find_figure(rows, LABELS["capacity"])

    print("attachment : %s" % attachment.get("title"))
    print("population : %s   (matched on %r)" % (population, pop_label))
    print("capacity   : %s   (matched on %r)" % (capacity, cap_label))

    if population is None or capacity is None or capacity < population * 0.8:
        previous = load_existing()
        previous["parser_status"] = "needs_review"
        previous["fetched_at"] = datetime.now(timezone.utc).isoformat()
        previous["note"] = (
            "The weekly file was downloaded but the expected labels were not matched, "
            "or the figures failed the sanity check. Previous values retained. "
            "Inspect data/_sheet-dump.json and extend LABELS in "
            "scripts/fetch_prison_figures.py."
        )
        if not args.dry_run and previous:
            with open(OUT_PATH, "w", encoding="utf-8") as fh:
                json.dump(previous, fh, indent=2)
        print("PARSE INCOMPLETE. Previous figures kept; see data/_sheet-dump.json.", file=sys.stderr)
        return 2

    record = {
        "as_at": attachment_date(attachment),
        "published": payload.get("public_updated_at"),
        "population": population,
        "useable_operational_capacity": capacity,
        "headroom": capacity - population,
        "headroom_derived": True,
        "source_title": attachment.get("title"),
        "source_url": attachment.get("url"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "parser_status": "ok",
        "note": (
            "Read automatically from the Ministry of Justice weekly estate bulletin. "
            "Headroom is capacity less population, computed here."
        ),
    }

    print(json.dumps(record, indent=2))
    if args.dry_run:
        return 0

    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

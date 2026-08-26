#!/usr/bin/env python3
"""Resolve and download the Home Office open data files, and write the manifest.

The landing page is hardcoded. The asset URLs are not, because they change at
every quarterly release. The page is parsed, the current asset URLs are
resolved, each file is downloaded once, and data/manifest.json records where
each file came from, when it was retrieved and what its SHA256 was.

Raw files are gitignored. The manifest is committed, so anyone can rebuild
data/raw/ and confirm they hold the same bytes we did.

Usage:
    python etl/fetch.py --dry-run      list what was discovered, download nothing
    python etl/fetch.py                download everything and write the manifest
    python etl/fetch.py --from 2018    restrict to financial years starting 2018
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    normalise_financial_year,
    resolve_data_root,
    write_json,
)

LANDING_PAGE = (
    "https://www.gov.uk/government/statistical-data-sets/"
    "police-recorded-crime-and-outcomes-open-data-tables"
)

USER_AGENT = (
    "oocd-dashboard/1.0 (research dashboard, Oxon Advisory; "
    "contact admin@oxonadvisory.com) python-requests"
)

# Politeness: one request at a time, with a pause between them.
REQUEST_DELAY_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 120
CHUNK_BYTES = 1 << 16

DATA_EXTENSIONS = (".xlsx", ".xls", ".csv", ".ods", ".zip")

EARLIEST_FINANCIAL_YEAR_START = 2014

KIND_OUTCOMES = "outcomes_open_data"
KIND_FORCE_AREA_CRIME = "police_force_area_crime"
KIND_USER_GUIDE = "user_guide"
KIND_OTHER = "other"


@dataclass
class Asset:
    """One downloadable file discovered on the landing page."""

    kind: str
    url: str
    title: str
    section: str
    filename: str
    financial_year: str | None
    financial_years: tuple[str, ...] = ()
    reason: str = ""


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _nearest_heading(node) -> str:
    """Return the text of the closest heading above a node, or an empty string."""
    for candidate in node.find_all_previous(["h1", "h2", "h3", "h4"], limit=6):
        text = re.sub(r"\s+", " ", candidate.get_text(" ", strip=True))
        if text:
            return text
    return ""


# Classification is led by the link title, not by the heading above it.
#
# The landing page lists a good deal more than the two series used here, and
# several of the others sit under the same headings. An earlier version matched
# on the heading as well as the title, and picked up the alternate offences
# file, the firearms and knives subsets, two subcode files, a supplementary
# metrics file and a geographical reference table. Taking the alternate offences
# file in particular would have double counted, because it holds outcome types
# 1a, 2a and 3a, which are already inside outcomes 1, 2 and 3.
#
# The two series are identified by a phrase that appears in their titles and in
# no other title on the page.
OUTCOMES_TITLE_RE = re.compile(r"\boutcomes\s+open\s+data\b", re.IGNORECASE)
FORCE_AREA_TITLE_RE = re.compile(r"\bpolice\s+force\s+area\b", re.IGNORECASE)
USER_GUIDE_TITLE_RE = re.compile(r"\buser\s*guide\b", re.IGNORECASE)

# A second guard. If one of these appears in a title, the file is a subset, a
# derived metric or a lookup, never one of the two series, whatever else the
# title says. Each is a file seen on the page on 23 July 2026.
NOT_THE_SERIES = (
    ("alternate", "outcome types 1a, 2a and 3a, already inside outcomes 1, 2 and 3"),
    ("alternative", "alternative offence subset"),
    ("subcode", "offence subcode breakdown, not the main series"),
    ("supplementary", "derived metrics, not the source series"),
    ("firearm", "firearms subset of the outcomes series"),
    ("knive", "knives subset of the outcomes series"),
    ("knife", "knives subset of the outcomes series"),
    ("sharp instrument", "knives subset of the outcomes series"),
    ("geographical reference", "lookup table, carries no counts"),
)


def _classify(title: str) -> tuple[str, str]:
    """Decide what a file is from its title. Returns (kind, reason).

    The reason is reported for everything, including what was passed over, so a
    file the page adds later is visible rather than silently ignored.
    """
    text = title.lower()

    for token, reason in NOT_THE_SERIES:
        if token in text:
            return KIND_OTHER, reason

    if USER_GUIDE_TITLE_RE.search(title):
        return KIND_USER_GUIDE, "user guide"
    if OUTCOMES_TITLE_RE.search(title):
        return KIND_OUTCOMES, "outcomes open data series"
    if FORCE_AREA_TITLE_RE.search(title):
        return KIND_FORCE_AREA_CRIME, "police force area crime series"
    return KIND_OTHER, "neither of the two series this dashboard uses"


def discover_assets(html: str, base_url: str = LANDING_PAGE) -> list[Asset]:
    """Find every downloadable data file linked from the landing page.

    Pure function over the page HTML, so it can be tested against a saved copy
    of the page without touching the network.
    """
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    assets: list[Asset] = []

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        url = urljoin(base_url, href)
        path = urlparse(url).path
        if not path.lower().endswith(DATA_EXTENSIONS):
            continue
        if url in seen:
            continue
        seen.add(url)

        title = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True))
        section = _nearest_heading(anchor)
        filename = Path(urlparse(url).path).name
        kind, reason = _classify(title or filename)
        covered = financial_years_covered(title or filename)

        assets.append(
            Asset(
                kind=kind,
                url=url,
                title=title or filename,
                section=section,
                filename=filename,
                financial_year=covered[0] if len(covered) == 1 else None,
                financial_years=covered,
                reason=reason,
            )
        )

    return assets


COMPACT_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})[ _-]?(\d{2})(?!\d)")

# The published link titles name the year the financial year ends in, as in
# "Outcomes open data, year ending March 2026", which is financial year 2025/26.
# A file can also cover a range: "year ending March 2006 to year ending March
# 2014" is 2005/06 to 2013/14.
YEAR_ENDING_RE = re.compile(r"years?\s+ending\s+March\s+(20\d{2})", re.IGNORECASE)

# The force area tables are titled differently again: "from March 2008 to March
# 2012" with no "ending", and "year ending March 2013 onwards" for the current
# file, which has no end year at all.
BARE_MARCH_RE = re.compile(r"March\s+(20\d{2})", re.IGNORECASE)
OPEN_ENDED_RE = re.compile(r"\bonwards?\b", re.IGNORECASE)

# Stands for "covers every year from its first to the latest published".
OPEN_ENDED = "onwards"


def _financial_year_ending(calendar_year: int) -> str:
    """'year ending March 2026' is financial year 2025/26."""
    start = calendar_year - 1
    return f"{start}/{calendar_year % 100:02d}"


def financial_years_covered(text: str) -> tuple[str, ...]:
    """Every financial year a title says the file covers, earliest first.

    Handles the three forms the landing page uses: an explicit financial year,
    a year ending March, and a range of years ending March.
    """
    open_ended = bool(OPEN_ENDED_RE.search(text))

    ending = [int(match.group(1)) for match in YEAR_ENDING_RE.finditer(text)]
    if not ending:
        ending = [int(match.group(1)) for match in BARE_MARCH_RE.finditer(text)]
    if ending:
        first, last = min(ending), max(ending)
        years = tuple(_financial_year_ending(year) for year in range(first, last + 1))
        return years + (OPEN_ENDED,) if open_ended else years

    explicit = normalise_financial_year(text)
    if explicit:
        return (explicit,)

    compact = _year_from_compact(text)
    return (compact,) if compact else ()


def _year_from_compact(text: str) -> str | None:
    """Read financial years written without a separator, such as '201415'."""
    for match in COMPACT_YEAR_RE.finditer(text):
        start = int(match.group(1))
        end = 2000 + int(match.group(2))
        if end == start + 1:
            return f"{start}/{end % 100:02d}"
    return None


def select_assets(assets: list[Asset], from_year: int) -> list[Asset]:
    """Keep the outcomes series, the force area crime tables and the user guide."""
    selected: list[Asset] = []
    for asset in assets:
        if asset.kind == KIND_OTHER:
            continue
        if asset.kind in (KIND_OUTCOMES, KIND_FORCE_AREA_CRIME):
            if not asset.financial_years:
                # A file we cannot date is kept and reported, never guessed at.
                # transform.py takes the year from the rows.
                selected.append(asset)
                continue
            if OPEN_ENDED in asset.financial_years:
                # Runs to the latest published year, so it always qualifies.
                selected.append(asset)
                continue
            latest = max(
                int(year.split("/")[0])
                for year in asset.financial_years
                if year != OPEN_ENDED
            )
            if latest < from_year:
                # Wholly before the period covered here. The pre 2014 outcomes
                # archive and the two older force area archives are all in this
                # case.
                continue
        selected.append(asset)
    return selected


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(manifest_path: Path) -> dict:
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8") as handle:
            return json.load(handle)
    return {}


def _existing_entry(manifest: dict, filename: str) -> dict | None:
    for entry in manifest.get("files", []):
        if entry.get("filename") == filename:
            return entry
    return None


def download(
    session: requests.Session, asset: Asset, previous: dict | None, raw_dir: Path
) -> dict:
    """Download one asset, or keep the local copy when the checksum matches."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / asset.filename

    if previous and target.exists():
        local_sha = sha256_of(target)
        if local_sha == previous.get("sha256") and previous.get("url") == asset.url:
            print(f"  unchanged, keeping local copy: {asset.filename}")
            entry = dict(previous)
            entry["reused_local_copy"] = True
            return entry

    print(f"  downloading: {asset.filename}")
    response = session.get(asset.url, stream=True, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    partial = target.with_suffix(target.suffix + ".part")
    with partial.open("wb") as handle:
        for chunk in response.iter_content(CHUNK_BYTES):
            handle.write(chunk)
    partial.replace(target)

    time.sleep(REQUEST_DELAY_SECONDS)

    return {
        "kind": asset.kind,
        "filename": asset.filename,
        "title": asset.title,
        "section": asset.section,
        "financial_year": asset.financial_year,
        "financial_years": list(asset.financial_years),
        "url": asset.url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "size_bytes": target.stat().st_size,
        "sha256": sha256_of(target),
        "reused_local_copy": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what was discovered on the landing page, download nothing",
    )
    parser.add_argument(
        "--from",
        dest="from_year",
        type=int,
        default=EARLIEST_FINANCIAL_YEAR_START,
        help="earliest financial year start to download, default 2014",
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help="data directory to write into. Defaults to data/.",
    )
    args = parser.parse_args()
    paths = resolve_data_root(args.data_root)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    print(f"Reading the landing page: {LANDING_PAGE}")
    response = session.get(LANDING_PAGE, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    assets = discover_assets(response.text, LANDING_PAGE)
    selected = select_assets(assets, args.from_year)

    by_kind: dict[str, list[Asset]] = {}
    for asset in selected:
        by_kind.setdefault(asset.kind, []).append(asset)

    print(f"\nDiscovered {len(assets)} data files, selected {len(selected)}.")
    for kind in (KIND_OUTCOMES, KIND_FORCE_AREA_CRIME, KIND_USER_GUIDE):
        group = by_kind.get(kind, [])
        print(f"\n{kind}: {len(group)}")
        for asset in sorted(
            group, key=lambda a: (a.financial_years[0] if a.financial_years else "", a.filename)
        ):
            years = [y for y in asset.financial_years if y != OPEN_ENDED]
            if OPEN_ENDED in asset.financial_years and years:
                span = f"{years[0]} onwards"
            elif len(years) > 1:
                span = f"{years[0]} to {years[-1]}"
            else:
                span = asset.financial_year or (years[0] if years else "no year")
            print(f"  [{span}] {asset.title}")
            print(f"      {asset.url}")

    passed_over = [a for a in assets if a.kind == KIND_OTHER]
    if passed_over:
        print(f"\nPassed over: {len(passed_over)} files")
        for asset in sorted(passed_over, key=lambda a: a.title):
            print(f"  {asset.title}")
            print(f"      {asset.reason}")

    undated = [a for a in by_kind.get(KIND_OUTCOMES, []) if not a.financial_years]
    if undated:
        print(
            f"\nWARNING: {len(undated)} outcomes files carry no readable financial "
            "year. Every published one is titled by the year it ends in, so this "
            "means a title has changed. They are included, and the year will be "
            "taken from the file contents at transform time."
        )

    if not by_kind.get(KIND_OUTCOMES):
        print(
            "\nERROR: no outcomes open data files were found. The landing page "
            "markup has probably changed. Inspect the page and update "
            "discover_assets in etl/fetch.py rather than hardcoding asset URLs.",
            file=sys.stderr,
        )
        return 2

    if args.dry_run:
        print("\nDry run, nothing downloaded.")
        return 0

    previous_manifest = load_manifest(paths.manifest)
    entries: list[dict] = []
    print("\nDownloading:")
    for asset in selected:
        entry = download(
            session,
            asset,
            _existing_entry(previous_manifest, asset.filename),
            paths.raw,
        )
        entries.append(entry)

    manifest = {
        "provenance": "home_office_open_data",
        "landing_page": LANDING_PAGE,
        "licence": "Open Government Licence v3.0",
        "attribution": (
            "Contains public sector information licensed under the Open "
            "Government Licence v3.0. Source: Home Office, police recorded "
            "crime and outcomes open data tables."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "earliest_financial_year_requested": args.from_year,
        "files": sorted(entries, key=lambda e: e["filename"]),
    }
    write_json(paths.manifest, manifest)
    print(f"\nWrote {paths.manifest}")
    print(f"  {len(entries)} files, provenance home_office_open_data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

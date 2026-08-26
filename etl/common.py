"""Shared definitions for the out of court disposals ETL.

Everything that the rest of the pipeline needs to agree on lives here: the
outcome type classification, the canonical force list, header normalisation and
the small helpers used by more than one script.

Nothing in this module reads the network or the filesystem.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MANIFEST_PATH = DATA_DIR / "manifest.json"
ANNOTATIONS_PATH = REPO_ROOT / "etl" / "annotations.yml"

# Synthetic fixtures live in their own tree, which is gitignored in full, so
# invented numbers can never be committed into data/processed/ by accident.
FIXTURE_DATA_DIR = DATA_DIR / "fixture"


@dataclass(frozen=True)
class DataPaths:
    """The three paths every script needs, rooted at one data directory."""

    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def processed(self) -> Path:
        return self.root / "processed"

    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    @property
    def is_fixture(self) -> bool:
        return self.root.resolve() == FIXTURE_DATA_DIR.resolve()


def resolve_data_root(value: str | Path | None) -> DataPaths:
    """Turn a --data-root argument into the paths the scripts use.

    Accepts the word 'fixture' as a shorthand for the fixture tree.
    """
    if value is None:
        return DataPaths(DATA_DIR)
    if str(value) == "fixture":
        return DataPaths(FIXTURE_DATA_DIR)
    return DataPaths(Path(value))

# ---------------------------------------------------------------------------
# Outcome classification
# ---------------------------------------------------------------------------
# Source: Home Office, police recorded crime and outcomes open data tables user
# guide, and the crime outcomes technical annex. Recorded in
# docs/METHODOLOGY.md with the citation.

OUTCOME_LABELS: dict[int, str] = {
    0: "Not yet assigned an outcome",
    1: "Charged or summonsed",
    2: "Caution, youths",
    3: "Caution, adults",
    4: "Taken into consideration",
    5: "Offender died",
    6: "Penalty notices for disorder",
    7: "Cannabis or khat warning",
    8: "Community resolution",
    9: "Not in the public interest, Crown Prosecution Service",
    10: "Not in the public interest, police",
    11: "Prosecution prevented, suspect under age",
    12: "Prosecution prevented, suspect too ill",
    13: "Prosecution prevented, victim or key witness dead or too ill",
    14: "Evidential difficulties, suspect not identified, victim does not support further action",
    15: "Evidential difficulties, suspect identified, victim supports action",
    16: "Evidential difficulties, suspect identified, victim does not support further action",
    17: "Prosecution time limit expired",
    18: "Investigation complete, no suspect identified",
    19: "National Fraud Intelligence Bureau, fraud case",
    20: "Responsibility for further investigation transferred to another body",
    21: "Further investigation to support formal action not in the public interest, police decision",
    22: "Diversionary, educational or intervention activity",
}

# Outcome type 0 is not an outcome. It counts offences that have not yet been
# assigned one, and it is present in the published tables as a row like any
# other. It must never enter a total: including it in all assigned outcomes
# would put offences with no decision into the denominator of a measure about
# decisions. Confirmed present in the year ending March 2026 file, 32,384 rows.
NOT_ASSIGNED_TYPE = 0

# Types that must appear in the data, because the classification depends on
# them. A type outside this set can legitimately be absent from a year: the
# year ending March 2026 file carries no type 19, for instance.
ESSENTIAL_TYPES: tuple[int, ...] = (1, 2, 3, 6, 7, 8, 22)

# The six out of court disposal types. Outcome 4, taken into consideration, is
# deliberately absent: it is an admission recorded alongside a prosecution, not
# a disposal made instead of one.
OOCD_TYPES: tuple[int, ...] = (2, 3, 6, 7, 8, 22)

# The comparator: the case went to court.
CHARGE_TYPES: tuple[int, ...] = (1,)

# A positive outcome is one where somebody was held to account, by a charge or
# by an out of court disposal.
POSITIVE_TYPES: tuple[int, ...] = tuple(sorted(CHARGE_TYPES + OOCD_TYPES))

# Short labels used on charts, where the full label will not fit.
OOCD_SHORT_LABELS: dict[int, str] = {
    2: "Caution, youths",
    3: "Caution, adults",
    6: "Penalty notice",
    7: "Cannabis warning",
    8: "Community resolution",
    22: "Outcome 22",
}


def classify_outcome(outcome_type: int) -> str:
    """Return one of 'oocd', 'charge' or 'other' for an outcome type."""
    if outcome_type in OOCD_TYPES:
        return "oocd"
    if outcome_type in CHARGE_TYPES:
        return "charge"
    return "other"


# ---------------------------------------------------------------------------
# Count bases
# ---------------------------------------------------------------------------
# The two count columns are not interchangeable. Outcomes attributed to crimes
# recorded in the quarter undercount recent quarters because investigations are
# still open, so the closed basis is the default for describing decision
# behaviour. See docs/METHODOLOGY.md.

BASIS_CLOSED = "closed"
BASIS_RECORDED = "recorded"
COUNT_BASES: tuple[str, str] = (BASIS_CLOSED, BASIS_RECORDED)
DEFAULT_BASIS = BASIS_CLOSED

BASIS_LABELS: dict[str, str] = {
    BASIS_CLOSED: "Outcomes for investigations closed in the quarter",
    BASIS_RECORDED: "Outcomes for offences recorded in the quarter",
}


# ---------------------------------------------------------------------------
# Forces
# ---------------------------------------------------------------------------

TERRITORIAL_FORCES: tuple[str, ...] = (
    "Avon and Somerset",
    "Bedfordshire",
    "Cambridgeshire",
    "Cheshire",
    "City of London",
    "Cleveland",
    "Cumbria",
    "Derbyshire",
    "Devon and Cornwall",
    "Dorset",
    "Durham",
    "Dyfed-Powys",
    "Essex",
    "Gloucestershire",
    "Greater Manchester",
    "Gwent",
    "Hampshire",
    "Hertfordshire",
    "Humberside",
    "Kent",
    "Lancashire",
    "Leicestershire",
    "Lincolnshire",
    "Merseyside",
    "Metropolitan Police",
    "Norfolk",
    "North Wales",
    "North Yorkshire",
    "Northamptonshire",
    "Northumbria",
    "Nottinghamshire",
    "South Wales",
    "South Yorkshire",
    "Staffordshire",
    "Suffolk",
    "Surrey",
    "Sussex",
    "Thames Valley",
    "Warwickshire",
    "West Mercia",
    "West Midlands",
    "West Yorkshire",
    "Wiltshire",
)

BTP = "British Transport Police"

CANONICAL_FORCES: tuple[str, ...] = TERRITORIAL_FORCES + (BTP,)

# Forces excluded from per capita and per recorded crime comparison by default,
# because the denominator does not mean the same thing for them. British
# Transport Police polices the railway network and has no resident population.
NO_POPULATION_FORCES: frozenset[str] = frozenset({BTP})

# Names that appear in the published files but are not the canonical form. The
# key is the normalised published name, the value is the canonical name.
FORCE_ALIASES: dict[str, str] = {
    "metropolitan police service": "Metropolitan Police",
    "metropolitan": "Metropolitan Police",
    "london, city of": "City of London",
    "city of london police": "City of London",
    "hampshire and isle of wight": "Hampshire",
    "devon & cornwall": "Devon and Cornwall",
    "avon & somerset": "Avon and Somerset",
    "dyfed powys": "Dyfed-Powys",
    "dyfed-powys police": "Dyfed-Powys",
    "british transport police (btp)": BTP,
    "btp": BTP,
    "action fraud": "Action Fraud",
    "cifas": "Cifas",
    "financial fraud action uk": "Financial Fraud UK",
    "uk finance": "Financial Fraud UK",
}

# Rows carrying these names are central fraud reporting bodies, not police
# forces. They appear in the force area tables and must be handled explicitly
# rather than counted as a 45th force.
CENTRAL_FRAUD_BODIES: frozenset[str] = frozenset(
    {"Action Fraud", "Cifas", "Financial Fraud UK"}
)


def canonical_force(name: str) -> str | None:
    """Map a published force name to its canonical form.

    Returns None when the name is not recognised, so callers can decide whether
    to fail or to report. Never guesses.
    """
    if name is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(name)).strip()
    if not cleaned:
        return None

    # Try the name as published first, then with a trailing force word removed.
    # The order matters: British Transport Police ends in "Police" but is the
    # canonical name, so stripping first would lose it.
    candidates = [cleaned]
    stripped = re.sub(
        r"\s+(Police(\s+Service)?|Constabulary)$", "", cleaned, flags=re.IGNORECASE
    ).strip()
    if stripped and stripped != cleaned:
        candidates.append(stripped)

    for candidate in candidates:
        lowered = candidate.lower()
        for canonical in CANONICAL_FORCES:
            if lowered == canonical.lower():
                return canonical
        for body in CENTRAL_FRAUD_BODIES:
            if lowered == body.lower():
                return body
        if lowered in FORCE_ALIASES:
            return FORCE_ALIASES[lowered]
    return None


def force_slug(name: str) -> str:
    """Return the URL slug for a force, for example 'avon-and-somerset'."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug


# ---------------------------------------------------------------------------
# Financial years and quarters
# ---------------------------------------------------------------------------

FINANCIAL_YEAR_RE = re.compile(r"(20\d{2})\s*[/–—-]\s*(\d{2}|20\d{2})")


def normalise_financial_year(value: object) -> str | None:
    """Return a financial year as '2014/15', or None if it cannot be read."""
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    match = FINANCIAL_YEAR_RE.search(text)
    if not match:
        return None
    start = int(match.group(1))
    end_raw = match.group(2)
    end = int(end_raw) if len(end_raw) == 4 else 2000 + int(end_raw)
    if end != start + 1:
        return None
    return f"{start}/{end % 100:02d}"


def financial_year_start(financial_year: str) -> int:
    """Return the calendar year a financial year label starts in."""
    return int(financial_year.split("/")[0])


def normalise_quarter(value: object) -> int | None:
    """Return a financial quarter as an integer 1 to 4, or None."""
    if value is None:
        return None
    text = str(value).strip()
    match = re.search(r"([1-4])", text)
    if not match:
        return None
    return int(match.group(1))


def quarter_key(financial_year: str, quarter: int) -> str:
    """Return a sortable quarter key, for example '2014/15 Q1'."""
    return f"{financial_year} Q{quarter}"


# ---------------------------------------------------------------------------
# Header introspection
# ---------------------------------------------------------------------------
# Column headers vary between years, so nothing is positional and nothing is
# assumed. Each field lists the normalised header forms that have been seen or
# are plausible. An unmapped header is an error, never a silent drop.


def normalise_header(value: object) -> str:
    """Reduce a header cell to a comparable key."""
    text = unicodedata.normalize("NFKD", str(value if value is not None else ""))
    text = text.replace(" ", " ")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


HEADER_SYNONYMS: dict[str, tuple[str, ...]] = {
    "financial_year": (
        "financial year",
        "fin year",
        "year",
        "financial year of recording",
    ),
    "financial_quarter": (
        "financial quarter",
        "fin quarter",
        "quarter",
        "financial quarter of recording",
    ),
    "force_name": (
        "force name",
        "force",
        "police force area",
        "pfa",
        "force area",
        "police force",
    ),
    "offence_code": ("offence code", "offence code number", "code"),
    "offence_description": ("offence description", "offence", "offence desc"),
    "offence_group": ("offence group", "group"),
    "offence_subgroup": ("offence subgroup", "subgroup", "offence sub group"),
    "offence_code_expired": (
        "offence code expired",
        "offence code expired flag",
        "expired",
        "offence code expired indicator",
    ),
    "outcome_description": ("outcome description", "outcome desc", "outcome"),
    "outcome_group": ("outcome group", "outcome type group"),
    "outcome_type": ("outcome type", "outcome type code", "outcome code"),
    "count_recorded": (
        "number of outcomes for offences that were recorded in the quarter",
        "outcomes for offences that were recorded in the quarter",
        "outcomes recorded in the quarter",
        "number of outcomes recorded in quarter",
        "outcomes for offences recorded in the quarter",
    ),
    "count_closed": (
        "number of outcomes for investigations that were closed in the quarter",
        "outcomes for investigations that were closed in the quarter",
        "outcomes for investigations closed in the quarter",
        "outcomes closed in the quarter",
        "number of outcomes closed in quarter",
    ),
    # Present in the police force area crime tables rather than the outcomes
    # tables, used for the recorded crime denominator.
    "recorded_crime_count": (
        "number of offences",
        "offences",
        "count",
        "number of recorded offences",
        "rolling year total number of offences",
    ),
}

REQUIRED_OUTCOME_FIELDS: tuple[str, ...] = (
    "financial_year",
    "financial_quarter",
    "force_name",
    "offence_code",
    "outcome_type",
    "count_recorded",
    "count_closed",
)


class HeaderMappingError(RuntimeError):
    """Raised when a header cannot be mapped. Never swallowed."""


@dataclass(frozen=True)
class HeaderMap:
    """The mapping from a workbook's headers to the fields the ETL uses."""

    by_field: dict[str, str]
    unmapped: tuple[str, ...]

    def column(self, field: str) -> str | None:
        return self.by_field.get(field)


def build_header_map(
    headers: list[object],
    required: tuple[str, ...] = REQUIRED_OUTCOME_FIELDS,
    allow_unmapped: bool = False,
) -> HeaderMap:
    """Map a list of raw header cells onto ETL field names.

    Raises HeaderMappingError when a required field is missing, when two
    headers claim the same field, or when a header cannot be mapped at all and
    allow_unmapped is False.
    """
    lookup: dict[str, str] = {}
    for field, synonyms in HEADER_SYNONYMS.items():
        for synonym in synonyms:
            lookup[normalise_header(synonym)] = field

    by_field: dict[str, str] = {}
    unmapped: list[str] = []
    collisions: list[str] = []

    for raw in headers:
        raw_text = str(raw) if raw is not None else ""
        key = normalise_header(raw_text)
        if not key:
            continue
        field = lookup.get(key)
        if field is None:
            unmapped.append(raw_text)
            continue
        if field in by_field:
            collisions.append(f"{field}: '{by_field[field]}' and '{raw_text}'")
            continue
        by_field[field] = raw_text

    if collisions:
        raise HeaderMappingError(
            "Two headers map to the same field, which would silently drop a "
            "column: " + "; ".join(collisions)
        )

    missing = [field for field in required if field not in by_field]
    if missing:
        raise HeaderMappingError(
            "Required fields have no matching header: "
            + ", ".join(missing)
            + ". Headers seen: "
            + ", ".join(str(h) for h in headers)
            + ". Add the published header to HEADER_SYNONYMS in etl/common.py."
        )

    if unmapped and not allow_unmapped:
        raise HeaderMappingError(
            "Headers could not be mapped and would be dropped silently: "
            + ", ".join(repr(h) for h in unmapped)
            + ". Add each to HEADER_SYNONYMS in etl/common.py, or pass "
            "allow_unmapped after confirming they carry nothing the ETL needs."
        )

    return HeaderMap(by_field=by_field, unmapped=tuple(unmapped))


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------


def to_int(value: object) -> int:
    """Read a count cell as an integer. Blank and ':' mean zero, not missing."""
    if value is None:
        return 0
    if isinstance(value, bool):
        raise ValueError(f"Refusing to read a boolean as a count: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != int(value):
            raise ValueError(f"Count is not a whole number: {value!r}")
        return int(value)
    text = str(value).strip().replace(",", "")
    if text in {"", ":", "-", "..", "*"}:
        return 0
    # The published tables use several not applicable forms, including
    # "N/A - Offence code expired" in the recorded column for retired codes and
    # a bare "N/A" in the closed column against outcome type 0. All of them mean
    # the count does not apply, which is zero for our purposes. Anything else
    # that is not a number is an error and must not be quietly read as zero.
    if text.lower().startswith(("n/a", "na -", "not applicable")):
        return 0
    try:
        return int(float(text))
    except ValueError as error:
        raise ValueError(
            f"Cannot read {text!r} as a count. If this is a new not applicable "
            "marker, add it to to_int in etl/common.py rather than letting it "
            "become a zero."
        ) from error


def truthy_flag(value: object) -> bool:
    """Read the offence code expired flag.

    The published files mark an expired code with a lower case 'x' and leave the
    cell empty otherwise. Other plausible markers are accepted so a change of
    convention does not silently read every code as current.
    """
    if value is None:
        return False
    return str(value).strip().lower() in {"x", "yes", "y", "true", "1", "expired"}


def write_json(path: Path, payload: object) -> None:
    """Write JSON with stable key order and a trailing newline, so it diffs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def read_json(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json_compact(path: Path, payload: object) -> None:
    """Write JSON with no whitespace, for files the site loads at build time.

    The diffable artefact for these tables is the matching CSV, which changes
    one line per changed record.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"), ensure_ascii=False)
        handle.write("\n")

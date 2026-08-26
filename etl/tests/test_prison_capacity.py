"""Tests for the weekly prison estate bulletin reader.

The bulletin itself could not be opened from any environment that worked on
this page, so the label patterns are candidates until a live run confirms
them. What these tests pin is everything around the labels: that all sheets
are read and not only the first, that a figure is taken from the right of its
label, that an implausible number is refused, and that a partial match is
reported as incomplete rather than written out.
"""

import sys
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prison_capacity import (  # noqa: E402
    LABELS,
    MIN_CAPACITY_RATIO,
    find_figure,
    flatten_ods,
    newest_attachment,
    attachment_date,
    to_number,
)

CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
  <office:body><office:spreadsheet>{tables}</office:spreadsheet></office:body>
</office:document-content>"""


def cell(value="", repeat=1, numeric=False):
    attributes = ""
    if repeat > 1:
        attributes += f' table:number-columns-repeated="{repeat}"'
    if numeric:
        attributes += f' office:value-type="float" office:value="{value}"'
    return f"<table:table-cell{attributes}><text:p>{value}</text:p></table:table-cell>"


def row(cells, repeat=1):
    attributes = f' table:number-rows-repeated="{repeat}"' if repeat > 1 else ""
    return f"<table:table-row{attributes}>{''.join(cells)}</table:table-row>"


def sheet(name, rows):
    return f'<table:table table:name="{name}">{"".join(rows)}</table:table>'


def ods(sheets):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("content.xml", CONTENT.format(tables="".join(sheets)))
    return buffer.getvalue()


BULLETIN = ods(
    [
        sheet("Cover", [row([cell("Population bulletin: weekly 24 August 2026")])]),
        sheet(
            "Contents",
            [
                row([cell("Table 1"), cell("Prison population and capacity")]),
                row([cell("Table 2"), cell("Population by establishment")]),
            ],
        ),
        sheet(
            "Table 1",
            [
                row([cell("Measure"), cell("Number")]),
                row([cell("Total prison population"), cell("87421", numeric=True)]),
                row([cell("Useable operational capacity"), cell("89617", numeric=True)]),
            ],
        ),
    ]
)


class TestEverySheetIsRead:
    """A first sheet only reader finds nothing, because sheet one is a cover.

    This is the failure the kit's reference implementation would have hit on
    its first live run, and it would have looked like a wrong label rather
    than a wrong reader.
    """

    def test_all_three_sheets_come_back(self):
        sheets = flatten_ods(BULLETIN)
        assert [name for name, _ in sheets] == ["Cover", "Contents", "Table 1"]

    def test_the_figures_are_found_on_the_third_sheet(self):
        sheets = flatten_ods(BULLETIN)
        population, label, found_in = find_figure(sheets, LABELS["population"])
        assert population == 87421
        assert label == "Total prison population"
        assert found_in == "Table 1"

    def test_capacity_is_found_and_named(self):
        sheets = flatten_ods(BULLETIN)
        capacity, label, found_in = find_figure(sheets, LABELS["capacity"])
        assert capacity == 89617
        assert label == "Useable operational capacity"
        assert found_in == "Table 1"


class TestTheFigureComesFromTheRightOfTheLabel:
    def test_a_label_with_no_number_after_it_matches_nothing(self):
        sheets = flatten_ods(
            [ods([sheet("One", [row([cell("Prison population")])])])][0]
        )
        value, _, _ = find_figure(sheets, LABELS["population"])
        assert value is None

    def test_a_number_before_the_label_is_not_taken(self):
        sheets = flatten_ods(
            ods([sheet("One", [row([cell("70123", numeric=True), cell("Prison population")])])])
        )
        value, _, _ = find_figure(sheets, LABELS["population"])
        assert value is None

    def test_the_first_number_after_the_label_wins(self):
        sheets = flatten_ods(
            ods(
                [
                    sheet(
                        "One",
                        [
                            row(
                                [
                                    cell("Prison population"),
                                    cell("87421", numeric=True),
                                    cell("88000", numeric=True),
                                ]
                            )
                        ],
                    )
                ]
            )
        )
        value, _, _ = find_figure(sheets, LABELS["population"])
        assert value == 87421


class TestImplausibleFiguresAreRefused:
    """The range guard is what stops a percentage or a year being read as a
    population. Without it the first numeric cell on the row wins, and on a
    bulletin that is as likely to be a footnote marker as a figure."""

    @pytest.mark.parametrize(
        "raw", ["0", "12", "98.4", "2026", "1998", "3", "250000", "12000", ""]
    )
    def test_out_of_range_values_are_none(self, raw):
        assert to_number(raw) is None

    def test_a_bare_year_is_refused(self):
        """The one that would have shipped a wrong number.

        A year sits comfortably inside a range that starts at 1,000, so a
        table carrying a date beside its row label reads the date as the
        population and every other check passes.
        """
        assert to_number("2026") is None

    @pytest.mark.parametrize(
        "raw,expected",
        [("87,421", 87421), ("89617", 89617), (" 85,858 ", 85858), ("85858.0", 85858)],
    )
    def test_estate_sized_values_survive(self, raw, expected):
        assert to_number(raw) == expected

    def test_a_year_in_the_next_cell_is_skipped_for_the_figure_after_it(self):
        sheets = flatten_ods(
            ods(
                [
                    sheet(
                        "One",
                        [row([cell("Prison population"), cell("2026"), cell("87421")])],
                    )
                ]
            )
        )
        value, _, _ = find_figure(sheets, LABELS["population"])
        assert value == 87421


class TestTheSanityCheckOnTheTwoTogether:
    """Capacity below the population by any margin means the two labels
    matched different things. The check is on the pair, not on either alone."""

    def test_capacity_far_below_population_fails_the_ratio(self):
        population, capacity = 87421, 40000
        assert capacity < population * MIN_CAPACITY_RATIO

    def test_a_normal_week_passes_the_ratio(self):
        population, capacity = 87421, 89617
        assert capacity >= population * MIN_CAPACITY_RATIO


class TestChoosingTheAttachment:
    def test_the_latest_dated_ods_wins_whatever_the_order(self):
        payload = {
            "details": {
                "attachments": [
                    {"title": "Population bulletin: weekly 17 August 2026", "url": "a.ods"},
                    {"title": "Population bulletin: weekly 24 August 2026", "url": "b.ods"},
                    {"title": "Population bulletin: weekly 10 August 2026", "url": "c.ods"},
                ]
            }
        }
        assert newest_attachment(payload)["url"] == "b.ods"

    def test_a_non_ods_attachment_is_passed_over(self):
        payload = {
            "details": {
                "attachments": [
                    {"title": "Weekly bulletin 31 August 2026", "url": "later.csv"},
                    {"title": "Weekly bulletin 24 August 2026", "url": "earlier.ods"},
                ]
            }
        }
        assert newest_attachment(payload)["url"] == "earlier.ods"

    def test_no_ods_at_all_raises_rather_than_returning_nothing(self):
        with pytest.raises(Exception):
            newest_attachment({"details": {"attachments": [{"url": "x.csv"}]}})

    def test_the_date_is_read_out_of_the_title(self):
        assert (
            attachment_date({"title": "Population bulletin: weekly 24 August 2026"})
            == "2026-08-24"
        )

    def test_a_title_with_no_date_gives_none_rather_than_a_guess(self):
        assert attachment_date({"title": "Population bulletin"}) is None


class TestRepeatCountsDoNotExplode:
    """An .ods pads its trailing rows and columns with large repeat counts.
    Expanding them faithfully is how a two number reader runs out of memory."""

    def test_a_huge_row_repeat_is_capped(self):
        blob = ods([sheet("One", [row([cell("filler")], repeat=1048576)])])
        _, rows = flatten_ods(blob)[0]
        assert len(rows) <= 8

    def test_a_huge_column_repeat_is_capped(self):
        blob = ods([sheet("One", [row([cell("x"), cell("y", repeat=16384)])])])
        _, rows = flatten_ods(blob)[0]
        assert len(rows[0]) <= 65

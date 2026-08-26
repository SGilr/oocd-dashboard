"""Tests for reading ODS, the format the police force area crime tables use.

The reader streams the zip's content.xml rather than loading it, because the
published file is 14.2 MB compressed and expands to far more as XML. These
tests build small ODS files by hand so the parsing rules, particularly the
repeat counts, are pinned without needing the published file.
"""

import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transform import read_ods_rows, read_ods_sheets, read_rows  # noqa: E402

CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
  <office:body><office:spreadsheet>{tables}</office:spreadsheet></office:body>
</office:document-content>"""


def cell(value=None, repeat=1, numeric=False):
    attrs = ""
    if repeat > 1:
        attrs += f' table:number-columns-repeated="{repeat}"'
    if value is None:
        return f"<table:table-cell{attrs}/>"
    if numeric:
        return (
            f'<table:table-cell office:value-type="float" '
            f'office:value="{value}"{attrs}><text:p>{value}</text:p>'
            f"</table:table-cell>"
        )
    return (
        f'<table:table-cell office:value-type="string"{attrs}>'
        f"<text:p>{value}</text:p></table:table-cell>"
    )


def row(cells, repeat=1):
    attrs = f' table:number-rows-repeated="{repeat}"' if repeat > 1 else ""
    return f"<table:table-row{attrs}>{''.join(cells)}</table:table-row>"


def sheet(name, rows):
    return f'<table:table table:name="{name}">{"".join(rows)}</table:table>'


def write_ods(tmp_path, tables, name="test.ods"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        archive.writestr("content.xml", CONTENT.format(tables="".join(tables)))
    return path


class TestOdsReading:
    def test_reads_strings_and_numbers(self, tmp_path):
        path = write_ods(
            tmp_path,
            [sheet("Data", [
                row([cell("Financial Year"), cell("Force Name"), cell("Number of Offences")]),
                row([cell("2024/25"), cell("Kent"), cell(1234, numeric=True)]),
            ])],
        )
        rows = list(read_ods_rows(path))
        assert rows[0] == ["Financial Year", "Force Name", "Number of Offences"]
        assert rows[1] == ["2024/25", "Kent", 1234]

    def test_numbers_come_back_as_integers_not_floats(self, tmp_path):
        path = write_ods(tmp_path, [sheet("Data", [row([cell(42, numeric=True)])])])
        value = list(read_ods_rows(path))[0][0]
        assert value == 42
        assert isinstance(value, int)

    def test_a_repeated_cell_is_expanded(self, tmp_path):
        path = write_ods(
            tmp_path,
            [sheet("Data", [row([cell("a"), cell("b", repeat=3), cell("c")])])],
        )
        assert list(read_ods_rows(path))[0] == ["a", "b", "b", "b", "c"]

    def test_a_repeated_row_is_expanded(self, tmp_path):
        path = write_ods(
            tmp_path, [sheet("Data", [row([cell("x")], repeat=3)])]
        )
        assert list(read_ods_rows(path)) == [["x"], ["x"], ["x"]]

    def test_grid_padding_is_not_expanded(self, tmp_path):
        # A spreadsheet pads its last row out to the full column count. Taking
        # that literally would produce sixteen thousand empty cells per row.
        path = write_ods(
            tmp_path,
            [sheet("Data", [row([cell("a"), cell(None, repeat=16384)])])],
        )
        assert list(read_ods_rows(path))[0] == ["a"]

    def test_padding_rows_are_not_expanded(self, tmp_path):
        path = write_ods(
            tmp_path,
            [sheet("Data", [row([cell("a")]), row([cell(None)], repeat=1048576)])],
        )
        assert len(list(read_ods_rows(path))) == 2

    def test_trailing_empty_cells_are_trimmed(self, tmp_path):
        path = write_ods(
            tmp_path, [sheet("Data", [row([cell("a"), cell(None), cell(None)])])]
        )
        assert list(read_ods_rows(path))[0] == ["a"]

    def test_cover_sheets_are_skipped(self, tmp_path):
        path = write_ods(
            tmp_path,
            [
                sheet("Cover sheet", [row([cell("Title")])]),
                sheet("Notes", [row([cell("Some notes")])]),
                sheet("Table 1", [row([cell("Financial Year")])]),
            ],
        )
        assert list(read_ods_rows(path))[0] == ["Financial Year"]

    def test_every_sheet_is_available_by_name(self, tmp_path):
        path = write_ods(
            tmp_path,
            [
                sheet("Cover sheet", [row([cell("Title")])]),
                sheet("Table 1", [row([cell("a")])]),
                sheet("Table 2", [row([cell("b")])]),
            ],
        )
        names = [name for name, _ in read_ods_sheets(path)]
        assert names == ["Cover sheet", "Table 1", "Table 2"]

    def test_read_rows_dispatches_on_the_ods_extension(self, tmp_path):
        path = write_ods(tmp_path, [sheet("Data", [row([cell("a")])])])
        assert list(read_rows(path)) == [["a"]]

    def test_an_unsupported_extension_still_raises(self, tmp_path):
        path = tmp_path / "thing.docx"
        path.write_bytes(b"")
        with pytest.raises(ValueError, match="unsupported file type"):
            list(read_rows(path))

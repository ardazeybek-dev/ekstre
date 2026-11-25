"""Open an exported statement file and return its sheets as plain rows.

The file type is decided from the bytes, not the extension: many Turkish
banks hand out ``.xls`` files that are really HTML tables, and a ``.csv``
may be a renamed workbook.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime
from html.parser import HTMLParser

from .errors import StatementError

Row = list[object]
Sheet = list[Row]


def read_sheets(data: bytes) -> list[Sheet]:
    """Every sheet in the file as a list of rows, first sheet first."""
    head = data[:512].lstrip(b"\xef\xbb\xbf \t\r\n")
    if data.startswith(b"PK\x03\x04"):
        return _read_xlsx(data)
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        return _read_xls(data)
    if head[:1] == b"<":
        return _read_html(_decode(data))
    return [_read_csv(_decode(data))]


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1254"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


# --- xlsx -----------------------------------------------------------------

_DEFAULT_STYLE = {
    b"fills": b'<fill><patternFill patternType="none"/></fill>',
    b"fonts": b'<font><sz val="11"/><name val="Calibri"/></font>',
    b"borders": b"<border><left/><right/><top/><bottom/><diagonal/></border>",
}


def _reset_style_block(styles: bytes, block: bytes) -> bytes:
    pattern = re.compile(rb"<" + block + rb"[^>]*?(?:/>|>.*?</" + block + rb">)", re.DOTALL)
    match = pattern.search(styles)
    if not match:
        return styles
    count_match = re.search(rb'count="(\d+)"', match.group(0))
    count = max(1, min(int(count_match.group(1)) if count_match else 1, 10000))
    replacement = (
        b"<" + block + b' count="' + str(count).encode() + b'">'
        + _DEFAULT_STYLE[block] * count
        + b"</" + block + b">"
    )  # fmt: skip
    return pattern.sub(lambda _: replacement, styles, count=1)


def _strip_visual_styles(data: bytes) -> bytes:
    """Copy of the workbook with fills, fonts and borders reset to defaults.

    Files exported by bank portals or converted by other programs sometimes
    carry style definitions openpyxl rejects (``expected <class
    'openpyxl.styles.fills.Fill'>``). Those blocks only affect how cells look.
    Number formats and cell formats are left alone, because dates are stored
    as numbers and are only recognised as dates through them. Block sizes are
    kept so the style indexes stay valid.
    """
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            content = src.read(item.filename)
            if item.filename == "xl/styles.xml":
                for block in _DEFAULT_STYLE:
                    content = _reset_style_block(content, block)
            dst.writestr(item, content)
    return out.getvalue()


def _read_xlsx(data: bytes) -> list[Sheet]:
    import openpyxl

    try:
        book = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as first_error:
        try:
            book = openpyxl.load_workbook(
                io.BytesIO(_strip_visual_styles(data)), data_only=True, read_only=True
            )
        except Exception:
            raise StatementError(f"Could not open the Excel file: {first_error}") from first_error
    try:
        return [[list(row) for row in ws.iter_rows(values_only=True)] for ws in book.worksheets]
    finally:
        book.close()


# --- xls ------------------------------------------------------------------


def _read_xls(data: bytes) -> list[Sheet]:
    try:
        import xlrd
    except ImportError:
        raise StatementError(
            "This is an old .xls workbook. Install the extra reader with: pip install 'ekstre[xls]'"
        ) from None
    try:
        book = xlrd.open_workbook(file_contents=data)
    except Exception as error:
        raise StatementError(f"Could not open the .xls file: {error}") from error

    sheets: list[Sheet] = []
    for ws in book.sheets():
        sheet: Sheet = []
        for r in range(ws.nrows):
            row: Row = []
            for cell in ws.row(r):
                if cell.ctype == xlrd.XL_CELL_DATE:
                    value: object = xlrd.xldate_as_datetime(cell.value, book.datemode)
                    if isinstance(value, datetime) and value.time() == datetime.min.time():
                        value = value.date()
                elif cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                    value = None
                else:
                    value = cell.value
                row.append(value)
            sheet.append(row)
        sheets.append(sheet)
    return sheets


# --- HTML disguised as xls --------------------------------------------------


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[Sheet] = []
        self._depth = 0
        self._row: Row | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self.tables.append([])
        elif tag == "tr" and self._depth:
            self._finish_row()
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._finish_cell()
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th"):
            self._finish_cell()
        elif tag == "tr":
            self._finish_row()
        elif tag == "table" and self._depth:
            self._finish_row()
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def _finish_cell(self) -> None:
        if self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()) or None)
        self._cell = None

    def _finish_row(self) -> None:
        self._finish_cell()
        if self._row is not None and self.tables:
            self.tables[-1].append(self._row)
        self._row = None


def _read_html(text: str) -> list[Sheet]:
    parser = _TableParser()
    parser.feed(text)
    parser.close()
    if not parser.tables:
        raise StatementError("The file looks like HTML but contains no table.")
    # One sheet made of every table, so a header in one table and rows in
    # the next (a common export layout) still line up.
    return [[row for table in parser.tables for row in table]]


# --- csv ------------------------------------------------------------------


def _read_csv(text: str) -> Sheet:
    lines = text.splitlines()[:50]
    semicolons = sum(line.count(";") for line in lines)
    tabs = sum(line.count("\t") for line in lines)
    # Turkish exports use ";" because the comma is the decimal separator.
    delimiter = ","
    if semicolons or tabs:
        delimiter = ";" if semicolons >= tabs else "\t"
    return [list(row) for row in csv.reader(io.StringIO(text), delimiter=delimiter)]

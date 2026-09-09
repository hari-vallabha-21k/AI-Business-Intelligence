"""Workbook scanning: find the data inside a real spreadsheet.

Business exports rarely start with a header in cell A1. They carry title rows, a
merged banner, a cover sheet, blank spacer columns and a totals row at the
bottom. This module locates the actual table so the rest of the pipeline can
assume a clean frame:

1. read every sheet with no header assumption;
2. score each sheet and pick the one that looks like a data table;
3. find the header row within that sheet;
4. drop spacer rows/columns and trailing total rows.

Every decision is recorded on the returned report, so the interface can tell the
user what was read rather than silently picking something.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd

# How far down a sheet to look for a header before giving up.
MAX_HEADER_SCAN_ROWS = 25
# A header row must fill at least this share of the table's width.
MIN_HEADER_FILL = 0.6

_TOTAL_ROW = re.compile(
    r"^\s*(grand\s+)?(total|subtotal|sum|net\s+total)\s*[:\-]?\s*$", re.IGNORECASE
)
_PLACEHOLDER = re.compile(r"^(unnamed:\s*\d+|column\d+|field\d+|\d+)$", re.IGNORECASE)


# Delimiters seen in business exports, most likely first.
_DELIMITERS = (",", ";", "\t", "|")


def _sniff_delimiter(text: str) -> str:
    """Pick the delimiter that splits the file's body most consistently.

    pandas' own sniffing reads the first line, which in a real export is a
    report title with no delimiter at all -- that is how a comma-separated file
    ends up parsed on whitespace. Scoring whole lines avoids that.
    """
    lines = [line for line in text.splitlines()[:200] if line.strip()]
    if not lines:
        return ","

    best, best_score = ",", -1.0
    for delimiter in _DELIMITERS:
        counts = [line.count(delimiter) for line in lines]
        populated = [c for c in counts if c > 0]
        if len(populated) < max(2, len(lines) * 0.5):
            continue
        # Reward a high, consistent field count across the body.
        mode = max(set(populated), key=populated.count)
        consistency = populated.count(mode) / len(populated)
        score = consistency * 2 + min(mode, 20) / 20
        if score > best_score:
            best, best_score = delimiter, score
    return best


@dataclass
class ParseReport:
    """What the scanner did, in terms a user can check."""

    sheet_name: str | None = None
    sheets_available: list[str] = field(default_factory=list)
    header_row: int | None = None          # 1-based, as shown in Excel
    skipped_top_rows: int = 0
    dropped_total_rows: int = 0
    dropped_blank_columns: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "sheet_name": self.sheet_name,
            "sheets_available": self.sheets_available,
            "header_row": self.header_row,
            "skipped_top_rows": self.skipped_top_rows,
            "dropped_total_rows": self.dropped_total_rows,
            "dropped_blank_columns": self.dropped_blank_columns,
            "notes": self.notes,
        }


def _looks_like_label(value) -> bool:
    """Whether a cell could plausibly be a column heading."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    if isinstance(value, (int, float, pd.Timestamp)):
        return False
    text = str(value).strip()
    if not text or len(text) > 80:
        return False
    return not _PLACEHOLDER.match(text)


def _score_header_row(raw: pd.DataFrame, index: int, width: int) -> float:
    """How strongly row ``index`` looks like the header of the table below it."""
    row = raw.iloc[index]
    labels = [v for v in row if _looks_like_label(v)]
    if len(labels) < max(2, width * MIN_HEADER_FILL):
        return 0.0

    # Headings are distinct; a repeated value usually means a merged banner.
    distinct = len({str(v).strip().lower() for v in labels}) / len(labels)

    below = raw.iloc[index + 1 : index + 8]
    if below.empty:
        return 0.0
    # The rows underneath should be fuller than the rows above, and should
    # contain values that are not all text -- a table has data, not more titles.
    fill_below = float(below.notna().mean().mean())
    numeric_below = float(
        below.apply(lambda c: pd.to_numeric(c, errors="coerce").notna().mean()).mean()
    )
    coverage = len(labels) / width

    return coverage * 0.4 + distinct * 0.2 + fill_below * 0.25 + numeric_below * 0.15


def _find_header_row(raw: pd.DataFrame) -> int:
    """Index of the most header-like row in the first few rows of a sheet."""
    if raw.empty:
        return 0
    width = int(raw.notna().sum(axis=1).max() or 1)
    limit = min(MAX_HEADER_SCAN_ROWS, len(raw))

    best_index, best_score = 0, 0.0
    for index in range(limit):
        score = _score_header_row(raw, index, width)
        if score > best_score:
            best_index, best_score = index, score
    return best_index


def _promote_header(raw: pd.DataFrame, header_index: int) -> pd.DataFrame:
    """Use ``header_index`` as the column names and everything below as data."""
    header = raw.iloc[header_index]
    body = raw.iloc[header_index + 1 :].reset_index(drop=True)

    names, seen = [], {}
    for position, value in enumerate(header):
        name = str(value).strip() if _looks_like_label(value) else f"Column {position + 1}"
        # Excel allows repeated headings; make them unique without losing either.
        if name in seen:
            seen[name] += 1
            name = f"{name}.{seen[name]}"
        else:
            seen[name] = 0
        names.append(name)

    body.columns = names
    return body


def _drop_total_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove trailing total/subtotal rows, which are summaries and not records."""
    if df.empty:
        return df, 0

    def is_total(row) -> bool:
        text_cells = [str(v).strip() for v in row if isinstance(v, str) and str(v).strip()]
        if any(_TOTAL_ROW.match(cell) for cell in text_cells):
            return True
        # A row whose only text cell starts with "total" ("Total sales")
        return len(text_cells) == 1 and text_cells[0].lower().startswith("total")

    keep = [not is_total(row) for row in df.itertuples(index=False)]
    dropped = keep.count(False)
    return (df[keep].reset_index(drop=True), dropped) if dropped else (df, 0)


def _clean_frame(df: pd.DataFrame, report: ParseReport) -> pd.DataFrame:
    """Drop spacer rows and columns and trailing totals."""
    before_columns = len(df.columns)
    df = df.dropna(axis=0, how="all")
    # A column is a spacer only when it has no values at all.
    df = df.loc[:, df.notna().any()]
    report.dropped_blank_columns = before_columns - len(df.columns)

    df, dropped = _drop_total_rows(df)
    report.dropped_total_rows = dropped
    if dropped:
        report.notes.append(
            f"Ignored {dropped} total row(s) so they are not counted as transactions."
        )

    df.columns = [str(c).strip() for c in df.columns]
    return df.reset_index(drop=True)


def _sheet_score(df: pd.DataFrame) -> float:
    """Prefer the sheet that holds the largest real table."""
    if df.empty or not len(df.columns):
        return 0.0
    filled = float(df.notna().mean().mean())
    return len(df) * len(df.columns) * filled


def extract_table(
    content: bytes, filename: str, sheet: str | None = None
) -> tuple[pd.DataFrame, ParseReport]:
    """Find and return the data table in a workbook or delimited file."""
    report = ParseReport()
    lower = filename.lower()

    if lower.endswith((".csv", ".tsv")):
        text = content.decode("utf-8-sig", errors="replace")
        sep = "\t" if lower.endswith(".tsv") else _sniff_delimiter(text)
        # The widest line sets the column count, not the first one: a title line
        # holds a single field and would otherwise truncate the whole table.
        width = max((line.count(sep) + 1 for line in text.splitlines() if line.strip()), default=1)
        raw = pd.read_csv(
            io.StringIO(text), sep=sep, engine="python", header=None, dtype=object,
            # Blank lines are kept so the reported header row matches the row
            # number the user sees in their file; _clean_frame drops them later.
            skip_blank_lines=False, names=range(width),
        )
        return _finish(raw, report)

    book = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None, dtype=object)
    report.sheets_available = list(book)

    if sheet is not None:
        if sheet not in book:
            raise KeyError(sheet)
        report.sheet_name = sheet
        return _finish(book[sheet], report)

    # Score each sheet on its detected table, not its raw size: a cover sheet
    # with a long note must not beat a data sheet.
    best_name, best_frame, best_score = None, None, -1.0
    for name, raw in book.items():
        if raw.empty:
            continue
        candidate = _promote_header(raw, _find_header_row(raw))
        score = _sheet_score(candidate)
        if score > best_score:
            best_name, best_frame, best_score = name, raw, score

    if best_frame is None:
        return pd.DataFrame(), report

    report.sheet_name = best_name
    if len(book) > 1:
        report.notes.append(
            f"This workbook has {len(book)} sheets. We read '{best_name}' because it "
            "holds the largest table."
        )
    return _finish(book[best_name], report)


def _finish(raw: pd.DataFrame, report: ParseReport) -> tuple[pd.DataFrame, ParseReport]:
    header_index = _find_header_row(raw)
    report.header_row = header_index + 1
    report.skipped_top_rows = header_index
    if header_index:
        report.notes.append(
            f"Column names were read from row {header_index + 1}; the {header_index} row(s) "
            "above it look like a title rather than data."
        )
    return _clean_frame(_promote_header(raw, header_index), report), report

"""Read Excel/CSV uploads into a DataFrame (process doc sec. 3).

Validation lives here; finding the table inside the file is
``app.services.workbook``.
"""

from __future__ import annotations

import pandas as pd

from app.config import get_settings
from app.services.workbook import ParseReport, extract_table

SUPPORTED_EXTENSIONS = (".csv", ".tsv", ".xlsx", ".xlsm", ".xltx", ".xls")

# Signatures used to recognise a spreadsheet whose extension is wrong or absent.
_ZIP_MAGIC = b"PK\x03\x04"          # xlsx/xlsm are zip archives
_OLE_MAGIC = b"\xd0\xcf\x11\xe0"    # legacy xls is an OLE2 compound file


class FileError(ValueError):
    """A user-facing upload failure -- the message is shown as-is."""


def looks_like_excel(content: bytes) -> bool:
    return content.startswith(_ZIP_MAGIC) or content.startswith(_OLE_MAGIC)


def parse_upload(
    filename: str, content: bytes, sheet: str | None = None
) -> tuple[pd.DataFrame, ParseReport]:
    settings = get_settings()
    lower = (filename or "upload").lower()

    if not content:
        raise FileError("This file is empty. Please upload a file that contains data.")
    if len(content) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise FileError(f"This file is larger than the {limit_mb} MB upload limit.")

    # Trust the content over the name: exports are routinely saved as .xls while
    # actually being .xlsx, or arrive with no extension at all.
    if looks_like_excel(content) and not lower.endswith((".xlsx", ".xlsm", ".xltx", ".xls")):
        lower = f"{lower}.xlsx"
    elif not lower.endswith(SUPPORTED_EXTENSIONS):
        raise FileError(
            "We can only read Excel (.xlsx, .xlsm, .xls) and CSV files. "
            f"'{filename}' is not one of those formats."
        )

    try:
        df, report = extract_table(content, lower, sheet=sheet)
    except KeyError as exc:
        raise FileError(f"This file has no sheet named '{sheet}'.") from exc
    except ImportError as exc:
        # Older .xls needs a separate reader; say so instead of "corrupted".
        raise FileError(
            "This looks like an older Excel (.xls) file that we can't read yet. "
            "Please re-save it as .xlsx or CSV and upload again."
        ) from exc
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, never swallowed
        raise FileError(
            "We couldn't read this file. It may be corrupted or password protected."
        ) from exc

    if df.empty or not len(df.columns):
        if report.sheet_name:
            raise FileError(
                f"We couldn't find any data rows on sheet '{report.sheet_name}'. The sheet "
                "may contain only headings, or the data may be on another sheet."
            )
        raise FileError("We couldn't find any data rows in this file.")
    if len(df) > settings.max_rows_per_dataset:
        raise FileError(
            f"This file has {len(df):,} rows, above the "
            f"{settings.max_rows_per_dataset:,} row limit for a single upload."
        )

    return _coerce_types(df), report


def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Recover real dtypes.

    The scanner reads everything as ``object`` so that header detection sees raw
    cells. Numeric and date columns are restored here; anything ambiguous is
    left as text for the semantic engine and cleaning to judge.
    """
    from app.services.cleaning import clean_numeric, prefers_dayfirst

    out = df.copy()
    for column in out.columns:
        series = out[column]
        non_null = series.dropna()
        if non_null.empty or pd.api.types.is_numeric_dtype(series):
            continue

        numeric = clean_numeric(series)
        if numeric.notna().sum() >= 0.9 * len(non_null):
            out[column] = numeric
            continue

        if pd.api.types.is_datetime64_any_dtype(series):
            continue
        text = non_null.astype(str)
        if text.str.len().max() <= 40:
            parsed = pd.to_datetime(
                series, errors="coerce", format="mixed", dayfirst=prefers_dayfirst(series)
            )
            if parsed.notna().sum() >= 0.9 * len(non_null):
                out[column] = parsed

    return out

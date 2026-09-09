"""Read Excel/CSV uploads into a DataFrame (process doc sec. 3)."""

from __future__ import annotations

import io

import pandas as pd

from app.config import get_settings

SUPPORTED_EXTENSIONS = (".csv", ".tsv", ".xlsx", ".xlsm", ".xls")


class FileError(ValueError):
    """A user-facing upload failure -- the message is shown as-is."""


def parse_upload(filename: str, content: bytes) -> pd.DataFrame:
    settings = get_settings()
    lower = filename.lower()

    if not content:
        raise FileError("This file is empty. Please upload a file that contains data.")
    if len(content) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise FileError(f"This file is larger than the {limit_mb} MB upload limit.")
    if not lower.endswith(SUPPORTED_EXTENSIONS):
        raise FileError(
            "We can only read Excel (.xlsx, .xlsm, .xls) and CSV files. "
            f"'{filename}' is not one of those formats."
        )

    try:
        if lower.endswith((".csv", ".tsv")):
            sep = "\t" if lower.endswith(".tsv") else None
            df = pd.read_csv(io.BytesIO(content), sep=sep, engine="python")
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, never swallowed
        raise FileError(
            "We couldn't read this file. It may be corrupted or password protected."
        ) from exc

    df = _tidy(df)
    if df.empty:
        raise FileError("This file has no data rows once empty rows were removed.")
    if not len(df.columns):
        raise FileError("This file has no readable columns.")
    if len(df) > settings.max_rows_per_dataset:
        raise FileError(
            f"This file has {len(df):,} rows, above the "
            f"{settings.max_rows_per_dataset:,} row limit for a single upload."
        )
    return df


def _tidy(df: pd.DataFrame) -> pd.DataFrame:
    """Drop blank rows/columns and normalise header text."""
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    # Excel exports frequently carry Unnamed: 4 style placeholder headers.
    df = df.loc[:, [not str(c).startswith("Unnamed:") or df[c].notna().any() for c in df.columns]]
    return df.reset_index(drop=True)

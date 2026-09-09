"""Data profiling (PRD sec. 9): describe the file before interpreting it."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.semantic.engine import ColumnSignals
from app.services.cleaning import prefers_dayfirst

# Columns are only sniffed for dates on a sample; full parsing of a 500k-row
# text column is not worth the seconds it costs.
_DATE_SAMPLE = 200


def _numeric_share(series: pd.Series) -> float:
    non_null = series.dropna()
    if non_null.empty:
        return 0.0
    if pd.api.types.is_numeric_dtype(non_null) and not pd.api.types.is_bool_dtype(non_null):
        return 1.0
    coerced = pd.to_numeric(
        non_null.astype(str).str.replace(r"[,\s₹$€£]", "", regex=True), errors="coerce"
    )
    return float(coerced.notna().mean())


def _date_share(series: pd.Series) -> float:
    non_null = series.dropna()
    if non_null.empty:
        return 0.0
    if pd.api.types.is_datetime64_any_dtype(non_null):
        return 1.0
    if pd.api.types.is_numeric_dtype(non_null):
        return 0.0
    sample = non_null.head(_DATE_SAMPLE).astype(str)
    parsed = pd.to_datetime(
        sample, errors="coerce", format="mixed", dayfirst=prefers_dayfirst(sample)
    )
    return float(parsed.notna().mean())


def _safe_float(value) -> float | None:
    if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(out) or np.isinf(out)) else out


def profile_column(series: pd.Series, name: str) -> ColumnSignals:
    non_null = series.dropna()
    numeric_share = _numeric_share(series)
    stats: dict[str, float | None] = {"mean": None, "max_value": None, "min_value": None}

    if numeric_share >= 0.6 and not non_null.empty:
        as_num = pd.to_numeric(
            non_null.astype(str).str.replace(r"[,\s₹$€£]", "", regex=True), errors="coerce"
        ).dropna()
        if not as_num.empty:
            stats = {
                "mean": _safe_float(as_num.mean()),
                "max_value": _safe_float(as_num.max()),
                "min_value": _safe_float(as_num.min()),
            }

    return ColumnSignals(
        name=name,
        dtype=str(series.dtype),
        non_null=int(non_null.shape[0]),
        unique=int(non_null.nunique()),
        total=int(series.shape[0]),
        numeric_share=round(numeric_share, 3),
        date_share=round(_date_share(series), 3),
        **stats,
    )


def profile_dataframe(df: pd.DataFrame) -> tuple[dict, list[ColumnSignals]]:
    """Return a JSON-serialisable profile plus the signals the mapper consumes."""
    signals = [profile_column(df[c], str(c)) for c in df.columns]
    duplicate_rows = int(df.duplicated().sum())

    columns = []
    for sig in signals:
        series = df[sig.name]
        sample = [str(v) for v in series.dropna().unique()[:5]]
        columns.append(
            {
                "name": sig.name,
                "dtype": sig.dtype,
                "non_null": sig.non_null,
                "missing": sig.total - sig.non_null,
                "missing_pct": round(100 * (sig.total - sig.non_null) / sig.total, 2)
                if sig.total
                else 0.0,
                "unique": sig.unique,
                "numeric_share": sig.numeric_share,
                "date_share": sig.date_share,
                "mean": sig.mean,
                "min": sig.min_value,
                "max": sig.max_value,
                "sample_values": sample,
            }
        )

    profile = {
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "duplicate_rows": duplicate_rows,
        "columns": columns,
    }
    return profile, signals

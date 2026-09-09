"""Build canonical records from a mapped upload (process doc sec. 8-9).

Output rows are keyed by canonical concept, so every downstream component reads
the same shape regardless of what the source file called its columns. The raw
row travels alongside under ``_raw`` -- nothing the user uploaded is discarded.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.semantic.concepts import CONCEPTS, Role
from app.semantic.engine import MappingProposal
from app.services.cleaning import build_label_map, canonical_role, clean_dates, clean_numeric

# Dimensions whose spelling variants are folded together.
_NORMALISED_DIMENSIONS = ("BRANCH", "DEPARTMENT", "CATEGORY", "CHANNEL", "EXPENSE_CATEGORY")


def build_records(
    df: pd.DataFrame,
    proposals: list[MappingProposal],
    default_branch: str | None = None,
) -> tuple[list[dict], list[dict], date | None, date | None]:
    """Return (records, cleaning_log, period_start, period_end)."""
    accepted = [p for p in proposals if p.concept]
    if not accepted:
        return [], [], None, None

    canonical = pd.DataFrame(index=df.index)
    log: list[dict] = []

    for p in accepted:
        if p.source_column not in df.columns:
            continue
        meta = CONCEPTS[p.concept]
        source = df[p.source_column]

        if meta.role is Role.MEASURE:
            values = clean_numeric(source)
            dropped = int(source.notna().sum() - values.notna().sum())
            if dropped:
                log.append(
                    {
                        "type": "non_numeric_dropped",
                        "column": p.source_column,
                        "concept": p.concept,
                        "rows_affected": dropped,
                    }
                )
        elif meta.role is Role.TEMPORAL:
            values = clean_dates(source)
        else:
            values = source.astype("string").str.strip()
            if p.concept in _NORMALISED_DIMENSIONS:
                mapping, entries = build_label_map(values)
                values = values.map(lambda v: mapping.get(v, v) if pd.notna(v) else v)
                for entry in entries:
                    log.append({**entry, "column": p.source_column, "concept": p.concept})
            elif p.concept == "ROLE":
                normalised = values.map(lambda v: canonical_role(v) if pd.notna(v) else v)
                changed = int((normalised != values).sum())
                if changed:
                    log.append(
                        {
                            "type": "role_normalisation",
                            "column": p.source_column,
                            "concept": p.concept,
                            "rows_affected": changed,
                        }
                    )
                values = normalised

        # Several source columns can feed one additive measure (basic + gross pay).
        if p.concept in canonical.columns and meta.role is Role.MEASURE and meta.additive:
            canonical[p.concept] = canonical[p.concept].fillna(0) + values.fillna(0)
            log.append(
                {"type": "measure_combined", "column": p.source_column, "concept": p.concept}
            )
        else:
            canonical[p.concept] = values

    if "BRANCH" not in canonical.columns and default_branch:
        canonical["BRANCH"] = default_branch
        log.append(
            {
                "type": "branch_defaulted",
                "concept": "BRANCH",
                "value": default_branch,
                "rows_affected": int(len(canonical)),
            }
        )

    period_start = period_end = None
    if "DATE" in canonical.columns:
        # DATE has already been through clean_dates; keep the parsed values.
        parsed = pd.to_datetime(canonical["DATE"], errors="coerce")
        present = parsed.dropna()
        if not present.empty:
            period_start, period_end = present.min().date(), present.max().date()
        canonical["DATE"] = parsed.dt.strftime("%Y-%m-%d")

    records = []
    raw_rows = df.astype(object).where(pd.notna(df), None).to_dict(orient="records")
    canonical_rows = canonical.astype(object).where(pd.notna(canonical), None).to_dict(
        orient="records"
    )
    for canon, raw in zip(canonical_rows, raw_rows, strict=True):
        canon = {k: _jsonable(v) for k, v in canon.items()}
        canon["_raw"] = {str(k): _jsonable(v) for k, v in raw.items()}
        records.append(canon)

    return records, log, period_start, period_end


def _jsonable(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return None if pd.isna(value) else value
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if pd.isna(value):
        return None
    return str(value)


def records_to_frame(records: list[dict]) -> pd.DataFrame:
    """Canonical records back into a frame, without the preserved raw payload."""
    if not records:
        return pd.DataFrame()
    return pd.DataFrame([{k: v for k, v in r.items() if k != "_raw"} for r in records])

"""Business semantic layer (process doc sec. 9).

Loads every active dataset version for a business, filtered by branch and
period, and returns one canonical frame per entity kind. Everything above this
line -- analytics, comparison, problem detection -- works only on these frames
and never touches an uploaded file again.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.registry import Frames
from app.models import Dataset, DatasetVersion, EntityKind, MappingMemory
from app.services.cleaning import normalize_label
from app.services.ingest import records_to_frame


def load_frames(
    db: Session,
    business_id: int,
    branches: list[str] | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> Frames:
    return load_scoped(db, business_id, branches, period_start, period_end)[0]


def load_scoped(
    db: Session,
    business_id: int,
    branches: list[str] | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> tuple[Frames, list[str]]:
    """Frames for the requested scope, plus notes about what was left out.

    A dataset with no period at all -- a payroll or expense snapshot with no
    date column -- cannot be attributed to a month. Including it in every period
    would count one month's payroll in all of them, so it is excluded from any
    period-filtered request and the exclusion is reported rather than silently
    applied.
    """
    notes: list[str] = []
    versions = db.scalars(
        select(DatasetVersion)
        .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
        .where(Dataset.business_id == business_id, DatasetVersion.is_active.is_(True))
    ).all()

    by_kind: dict[str, list[pd.DataFrame]] = {}
    for version in versions:
        if version.entity_kind is EntityKind.UNKNOWN or not version.records:
            continue
        if version.period_start is None or version.period_end is None:
            if period_start or period_end:
                notes.append(
                    f"'{version.filename}' has no reporting period, so it is excluded from "
                    "period-filtered results. Set its period to include it."
                )
                continue
        elif not _version_overlaps(version, period_start, period_end):
            continue
        frame = records_to_frame(version.records)
        if frame.empty:
            continue
        frame = _filter_rows(frame, branches, period_start, period_end)
        if not frame.empty:
            by_kind.setdefault(version.entity_kind.value, []).append(frame)

    frames = {
        kind: pd.concat(parts, ignore_index=True) for kind, parts in by_kind.items() if parts
    }
    return frames, notes


def _version_overlaps(
    version: DatasetVersion, period_start: date | None, period_end: date | None
) -> bool:
    """Whether a version's declared period intersects the requested one."""
    if period_start and version.period_end < period_start:
        return False
    if period_end and version.period_start > period_end:
        return False
    return True


def _filter_rows(
    frame: pd.DataFrame,
    branches: list[str] | None,
    period_start: date | None,
    period_end: date | None,
) -> pd.DataFrame:
    if branches and "BRANCH" in frame.columns:
        wanted = {normalize_label(b) for b in branches}
        frame = frame[frame["BRANCH"].astype(str).map(normalize_label).isin(wanted)]

    if (period_start or period_end) and "DATE" in frame.columns:
        dates = pd.to_datetime(frame["DATE"], errors="coerce")
        mask = dates.notna()
        if period_start:
            mask &= dates >= pd.Timestamp(period_start)
        if period_end:
            mask &= dates <= pd.Timestamp(period_end)
        # Rows with no date are kept only when the version itself carries no dates.
        frame = frame[mask] if dates.notna().any() else frame

    return frame.reset_index(drop=True)


def load_mapping_memory(db: Session, business_id: int, entity_kind: str) -> dict[str, str | None]:
    """Confirmed mappings for this business, keyed by normalised column name."""
    from app.semantic.engine import normalize

    rows = db.scalars(
        select(MappingMemory).where(MappingMemory.business_id == business_id)
    ).all()
    memory: dict[str, str | None] = {}
    for row in rows:
        # Kind-specific memory beats generic memory for the same column name.
        key = normalize(row.source_column)
        if row.entity_kind.value == entity_kind or key not in memory:
            memory[key] = row.concept
    return memory


def known_concepts(db: Session, business_id: int, entity_kind: str) -> set[str]:
    """Concepts already seen for this kind, used to flag schema evolution."""
    versions = db.scalars(
        select(DatasetVersion)
        .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
        .where(Dataset.business_id == business_id)
    ).all()
    seen: set[str] = set()
    for version in versions:
        if version.entity_kind.value != entity_kind:
            continue
        for mapping in version.mappings:
            if mapping.concept:
                seen.add(mapping.concept)
    return seen

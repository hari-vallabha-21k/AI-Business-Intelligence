"""Business semantic layer (process doc sec. 9).

Loads every active dataset version for a business, filtered by branch and
period, and returns one canonical frame per entity kind. Everything above this
line -- analytics, comparison, problem detection -- works only on these frames
and never touches an uploaded file again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.registry import Frames
from app.models import Dataset, DatasetVersion, EntityKind, MappingMemory
from app.semantic.grain import detect_overlap
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


def load_data(
    db: Session,
    business_id: int,
    branches: list[str] | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> LoadedData:
    """Frames, notes and the dataset versions that actually contributed."""
    frames, notes, versions = _load(db, business_id, branches, period_start, period_end)
    return LoadedData(frames=frames, notes=notes, versions=versions)


@dataclass
class LoadedData:
    """The frames analytics will run on, plus where they came from."""

    frames: Frames
    notes: list[str] = field(default_factory=list)
    versions: list[DatasetVersion] = field(default_factory=list)


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
    frames, notes, _ = _load(db, business_id, branches, period_start, period_end)
    return frames, notes


def _load(
    db: Session,
    business_id: int,
    branches: list[str] | None,
    period_start: date | None,
    period_end: date | None,
) -> tuple[Frames, list[str], list[DatasetVersion]]:
    notes: list[str] = []
    versions = db.scalars(
        select(DatasetVersion)
        .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
        .where(Dataset.business_id == business_id, DatasetVersion.is_active.is_(True))
    ).all()

    by_kind: dict[str, list[tuple[DatasetVersion, pd.DataFrame]]] = {}
    for version in versions:
        if version.entity_kind in (EntityKind.UNKNOWN, EntityKind.REFERENCE):
            continue  # not a fact table: nothing here is aggregated
        if not version.records:
            continue
        if version.superseded_by_id is not None:
            continue  # a corrected upload replaced this one
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
            by_kind.setdefault(version.entity_kind.value, []).append((version, frame))

    frames: Frames = {}
    contributing: list[DatasetVersion] = []
    for kind, parts in by_kind.items():
        if not parts:
            continue
        kept, overlap_notes = _drop_overlapping(parts)
        notes.extend(overlap_notes)
        if kept:
            frames[kind] = pd.concat([frame for _, frame in kept], ignore_index=True)
            contributing.extend(version for version, _ in kept)

    return frames, notes, contributing


# Identifiers that establish two datasets describe the same underlying records.
_IDENTITY_CONCEPTS = ("ORDER_ID", "EMPLOYEE_ID")


def _shared_measures(left: pd.DataFrame, right: pd.DataFrame) -> set[str]:
    """Additive concepts present in both frames -- the only double-count risk."""
    from app.semantic.concepts import CONCEPTS, Role

    def measures(frame: pd.DataFrame) -> set[str]:
        return {
            str(c)
            for c in frame.columns
            if str(c) in CONCEPTS
            and CONCEPTS[str(c)].role is Role.MEASURE
            and frame[c].notna().any()
        }

    return measures(left) & measures(right)


def _periods_intersect(left: DatasetVersion, right: DatasetVersion) -> bool:
    """Whether two versions cover overlapping time. Unknown periods count as yes."""
    if None in (left.period_start, left.period_end, right.period_start, right.period_end):
        return True
    return left.period_start <= right.period_end and right.period_start <= left.period_end


def _drop_overlapping(
    parts: list[tuple[DatasetVersion, pd.DataFrame]],
) -> tuple[list[tuple[DatasetVersion, pd.DataFrame]], list[str]]:
    """Keep one dataset per set of underlying records (PRD sec. 9, Rule 5).

    An invoice table and its line items describe the same money at different
    grains. Summing both reports revenue twice. When two datasets are found to
    cover the same identifiers, the coarser grain wins -- the invoice total is
    what was billed -- and the decision is reported rather than applied
    silently.
    """
    if len(parts) < 2:
        return parts, []

    notes: list[str] = []
    dropped: set[int] = set()

    for i, (left_version, left) in enumerate(parts):
        if i in dropped:
            continue
        for j, (right_version, right) in enumerate(parts[i + 1 :], start=i + 1):
            if j in dropped:
                continue
            # Two datasets can only double count if they both carry the same
            # measure. A staff list and a payroll run share employee ids but
            # not money, so both are needed, not one.
            if not _shared_measures(left, right):
                continue
            # The same employees legitimately appear in every month's payroll.
            # Identical ids across non-overlapping periods are different facts.
            if not _periods_intersect(left_version, right_version):
                continue
            for concept in _IDENTITY_CONCEPTS:
                verdict = detect_overlap(left, right, concept)
                if not verdict.overlaps:
                    continue

                left_keys = tuple(left_version.grain.get("keys", ()) or ())
                right_keys = tuple(right_version.grain.get("keys", ()) or ())
                if left_keys == right_keys:
                    # Same grain and same records: one is a re-upload of the
                    # other, so the newer version wins.
                    loser = i if left_version.id < right_version.id else j
                else:
                    # Different grain: keep the coarser one.
                    loser = i if len(left_keys) > len(right_keys) else j

                keeper = j if loser == i else i
                dropped.add(loser)
                notes.append(
                    f"'{parts[loser][0].filename}' and '{parts[keeper][0].filename}' describe "
                    f"the same records ({verdict.reason}). Counting both would report the "
                    f"same {concept.replace('_', ' ').lower()}s twice, so "
                    f"'{parts[keeper][0].filename}' was used."
                )
                break
            if i in dropped:
                break

    return [part for index, part in enumerate(parts) if index not in dropped], notes


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

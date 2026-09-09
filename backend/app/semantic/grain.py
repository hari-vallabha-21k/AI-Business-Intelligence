"""Grain detection: what does one row of this dataset represent?

This is the difference between a correct revenue figure and one that is five
times too large. An invoice table and its line items describe the same money at
different grains; summing both counts it twice (PRD sec. 9).

Grain is expressed as the set of canonical concepts whose combination is unique
across rows -- the row key. ``{ORDER_ID}`` means one row per order,
``{ORDER_ID, PRODUCT}`` one row per order line, ``{EMPLOYEE_ID, DATE}`` one row
per employee per day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

import pandas as pd

from app.semantic.concepts import CONCEPTS, Role

# Concepts that can take part in a row key. Measures never can: two rows with
# the same amount are not the same row.
_KEY_ROLES = (Role.IDENTIFIER, Role.DIMENSION, Role.TEMPORAL)

# A key must identify at least this share of rows uniquely to be accepted;
# below it, real duplicates are more likely than a wrong key.
MIN_UNIQUENESS = 0.98
# Beyond this many candidate columns, stop trying larger combinations.
MAX_KEY_WIDTH = 3


@dataclass
class Grain:
    """What one row is, and how confident we are."""

    keys: tuple[str, ...] = ()
    confidence: float = 0.0
    description: str = "unknown"
    duplicate_rows: int = 0
    row_count: int = 0
    # True when no combination of columns identifies a row -- the dataset is
    # pre-aggregated, or it genuinely contains repeated records.
    is_ambiguous: bool = True

    def as_dict(self) -> dict:
        return {
            "keys": list(self.keys),
            "confidence": round(self.confidence, 3),
            "description": self.description,
            "duplicate_rows": self.duplicate_rows,
            "row_count": self.row_count,
            "is_ambiguous": self.is_ambiguous,
        }


_PHRASES: dict[tuple[str, ...], str] = {
    ("ORDER_ID",): "1 row = 1 order",
    ("ORDER_ID", "PRODUCT"): "1 row = 1 line on an order",
    ("ORDER_ID", "CATEGORY"): "1 row = 1 category line on an order",
    ("EMPLOYEE_ID",): "1 row = 1 employee",
    ("EMPLOYEE_ID", "DATE"): "1 row = 1 employee per day",
    ("EMPLOYEE_ID", "BRANCH"): "1 row = 1 employee at a branch",
    ("CUSTOMER_ID",): "1 row = 1 customer",
    ("PRODUCT",): "1 row = 1 product",
    ("BRANCH",): "1 row = 1 branch",
    ("BRANCH", "DATE"): "1 row = 1 branch per day",
    ("DATE",): "1 row = 1 day",
    ("EXPENSE_CATEGORY", "BRANCH", "DATE"): "1 row = 1 expense line",
}

# Looked up by sorted key so that column order never changes the description.
_GRAIN_PHRASES = {tuple(sorted(k)): v for k, v in _PHRASES.items()}


def describe(keys: tuple[str, ...]) -> str:
    if not keys:
        return "unknown -- no column combination identifies a row"
    phrase = _GRAIN_PHRASES.get(tuple(sorted(keys)))
    if phrase:
        return phrase
    readable = " + ".join(CONCEPTS[k].label.lower() if k in CONCEPTS else k for k in keys)
    return f"1 row = 1 {readable}"


def _candidate_columns(frame: pd.DataFrame) -> list[str]:
    """Columns that could form part of a row key, most selective first."""
    candidates = []
    for column in frame.columns:
        concept = CONCEPTS.get(str(column))
        if concept is None or concept.role not in _KEY_ROLES:
            continue
        distinct = frame[column].nunique(dropna=False)
        if distinct <= 1:
            continue  # a constant column adds nothing to a key
        candidates.append((column, distinct))
    candidates.sort(key=lambda item: -item[1])
    return [name for name, _ in candidates]


def _repeated_identifier(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    """The most selective identifier column whose values repeat, if any."""
    repeated = [
        (name, frame[name].nunique(dropna=False))
        for name in candidates
        if name in CONCEPTS
        and CONCEPTS[name].role is Role.IDENTIFIER
        and _uniqueness(frame, (name,)) < 1.0
    ]
    if not repeated:
        return None
    return max(repeated, key=lambda item: item[1])[0]


def _key_rank(keys: tuple[str, ...]) -> tuple[int, int]:
    """Prefer keys built from real identifiers, then from dimensions."""
    identifiers = sum(
        1 for k in keys if k in CONCEPTS and CONCEPTS[k].role is Role.IDENTIFIER
    )
    temporal = sum(1 for k in keys if k in CONCEPTS and CONCEPTS[k].role is Role.TEMPORAL)
    return identifiers, temporal


def _uniqueness(frame: pd.DataFrame, keys: tuple[str, ...]) -> float:
    if not keys:
        return 0.0
    return float(frame.drop_duplicates(subset=list(keys)).shape[0] / len(frame))


def detect_grain(frame: pd.DataFrame) -> Grain:
    """Find the smallest set of columns that identifies a row.

    Smallest matters: ``{ORDER_ID}`` and ``{ORDER_ID, PRODUCT, DATE}`` may both
    be unique, but only the first says what the dataset actually is.
    """
    rows = len(frame)
    if rows == 0:
        return Grain(row_count=0, description="empty dataset")

    candidates = _candidate_columns(frame)
    if not candidates:
        return Grain(row_count=rows, description="unknown -- no identifying columns")

    # A business identifier that repeats tells us the rows are children of it:
    # several lines per order, several days per employee. The row key must then
    # include it, even if some other column happens to be unique in this file.
    required = _repeated_identifier(frame, candidates)

    best: tuple[str, ...] | None = None
    best_score = 0.0
    for width in range(1, min(MAX_KEY_WIDTH, len(candidates)) + 1):
        # Collect every key of this width that works, then choose among them:
        # an accidentally-unique product name should not beat the order id that
        # the dataset is actually keyed on.
        working = [
            (combo, _uniqueness(frame, combo))
            for combo in combinations(candidates, width)
            if required is None or required in combo
        ]
        passing = [(combo, score) for combo, score in working if score >= MIN_UNIQUENESS]
        if passing:
            best, best_score = max(passing, key=lambda item: (_key_rank(item[0]), item[1]))
            break
        if working:
            combo, score = max(working, key=lambda item: item[1])
            if score > best_score:
                best, best_score = combo, score

    if best is None or best_score < MIN_UNIQUENESS:
        # No key found. Report the closest attempt so the user can see why.
        duplicates = int(rows - (rows * best_score)) if best else 0
        return Grain(
            keys=tuple(best or ()),
            confidence=round(best_score, 3),
            description="unknown -- rows are not uniquely identified",
            duplicate_rows=duplicates,
            row_count=rows,
            is_ambiguous=True,
        )

    duplicates = int(rows - frame.drop_duplicates(subset=list(best)).shape[0])
    return Grain(
        keys=tuple(best),
        confidence=round(best_score, 3),
        description=describe(tuple(best)),
        duplicate_rows=duplicates,
        row_count=rows,
        is_ambiguous=False,
    )


@dataclass
class OverlapVerdict:
    """Whether two datasets describe the same underlying records."""

    overlaps: bool
    shared_key: str | None = None
    overlap_ratio: float = 0.0
    reason: str = ""
    notes: list[str] = field(default_factory=list)


def detect_overlap(left: pd.DataFrame, right: pd.DataFrame, concept: str) -> OverlapVerdict:
    """Do these two datasets cover the same transactions?

    Used to stop an invoice table and its line items from being summed
    together. Identity is judged on shared values of a business identifier, not
    on column names.
    """
    if concept not in left.columns or concept not in right.columns:
        return OverlapVerdict(False, reason=f"{concept} is not present in both datasets")

    left_values = set(left[concept].dropna().astype(str))
    right_values = set(right[concept].dropna().astype(str))
    if not left_values or not right_values:
        return OverlapVerdict(False, reason=f"no {concept} values to compare")

    shared = left_values & right_values
    # Containment must hold in BOTH directions. Measuring only against the
    # smaller set would let a one-row correction "cover" a whole payroll run and
    # replace it.
    ratio = min(len(shared) / len(left_values), len(shared) / len(right_values))
    if ratio < 0.5:
        return OverlapVerdict(
            False, concept, ratio,
            f"only {ratio:.0%} of {concept} values are shared in both directions",
        )
    return OverlapVerdict(
        True,
        concept,
        ratio,
        f"{ratio:.0%} of {concept} values appear in both datasets",
    )

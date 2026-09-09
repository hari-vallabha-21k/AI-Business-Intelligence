"""Relationship discovery between datasets (PRD sec. 13).

Two columns having similar names is not a relationship. A relationship is a
claim that values in one dataset refer to rows in another, and joining on a
false one silently multiplies or drops money. So every candidate is validated
on the data before it is proposed:

* the referenced side must be (nearly) unique -- otherwise the join fans out;
* the referring values must actually be present on the other side;
* the types must be compatible.

Name similarity only ranks candidates that already passed those checks.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.semantic.engine import tokens

# Referenced keys must be this unique for a many-to-one join to be safe.
MIN_KEY_UNIQUENESS = 0.98
# Below this share of matching values, the columns are unrelated.
MIN_OVERLAP = 0.50
# Above this share of unmatched values, the link is real but broken.
ORPHAN_WARNING = 0.05


@dataclass
class Relationship:
    from_dataset: str
    from_column: str
    to_dataset: str
    to_column: str
    kind: str             # many-to-one | one-to-one | many-to-many
    confidence: float
    overlap: float        # share of "from" values found in "to"
    orphan_rate: float    # share of "from" values with no match
    reason: str
    is_safe_join: bool

    def as_dict(self) -> dict:
        return {
            "from_dataset": self.from_dataset,
            "from_column": self.from_column,
            "to_dataset": self.to_dataset,
            "to_column": self.to_column,
            "kind": self.kind,
            "confidence": round(self.confidence, 3),
            "overlap": round(self.overlap, 3),
            "orphan_rate": round(self.orphan_rate, 3),
            "reason": self.reason,
            "is_safe_join": self.is_safe_join,
        }


def _values(frame: pd.DataFrame, column: str) -> set[str]:
    return set(frame[column].dropna().astype(str).str.strip()) - {""}


def _uniqueness(frame: pd.DataFrame, column: str) -> float:
    non_null = frame[column].dropna()
    if non_null.empty:
        return 0.0
    return float(non_null.nunique() / len(non_null))


def _compatible(left: pd.Series, right: pd.Series) -> bool:
    """Reject pairs that cannot refer to each other regardless of overlap."""
    left_num = pd.api.types.is_numeric_dtype(left)
    right_num = pd.api.types.is_numeric_dtype(right)
    if left_num != right_num:
        # A numeric id can still be stored as text on one side, so only reject
        # when one side is clearly non-numeric text.
        text_side = right if left_num else left
        coerced = pd.to_numeric(text_side.dropna().astype(str), errors="coerce")
        if coerced.notna().mean() < 0.9:
            return False
    return True


def discover(
    datasets: dict[str, pd.DataFrame], min_confidence: float = 0.5
) -> list[Relationship]:
    """Find validated relationships between every pair of datasets."""
    found: list[Relationship] = []
    names = list(datasets)

    for from_name in names:
        for to_name in names:
            if from_name == to_name:
                continue
            found.extend(_pair(from_name, datasets[from_name], to_name, datasets[to_name]))

    found = [r for r in found if r.confidence >= min_confidence]
    found.sort(key=lambda r: r.confidence, reverse=True)
    return _drop_mirrors(found)


def _pair(
    from_name: str, from_frame: pd.DataFrame, to_name: str, to_frame: pd.DataFrame
) -> list[Relationship]:
    results = []
    if from_frame.empty or to_frame.empty:
        return results

    for to_column in to_frame.columns:
        to_uniqueness = _uniqueness(to_frame, to_column)
        if to_uniqueness < MIN_KEY_UNIQUENESS:
            continue  # not a key: joining to it would multiply rows
        to_values = _values(to_frame, to_column)
        if len(to_values) < 2:
            continue

        for from_column in from_frame.columns:
            if not _compatible(from_frame[from_column], to_frame[to_column]):
                continue
            from_values = _values(from_frame, from_column)
            if not from_values:
                continue

            matched = from_values & to_values
            overlap = len(matched) / len(from_values)
            if overlap < MIN_OVERLAP:
                continue

            orphan_rate = 1 - overlap
            from_uniqueness = _uniqueness(from_frame, from_column)
            kind = "one-to-one" if from_uniqueness >= MIN_KEY_UNIQUENESS else "many-to-one"

            # Name similarity is a tie-breaker, never the evidence itself.
            shared_tokens = tokens(from_column) & tokens(to_column)
            name_bonus = 0.1 if shared_tokens else 0.0
            confidence = min(0.9 * overlap + name_bonus, 0.99)

            reason = f"{overlap:.0%} of {from_name}.{from_column} values exist in {to_name}.{to_column}"
            if shared_tokens:
                reason += "; the column names agree"
            if orphan_rate > ORPHAN_WARNING:
                reason += f"; {orphan_rate:.0%} have no match"

            results.append(
                Relationship(
                    from_dataset=from_name,
                    from_column=from_column,
                    to_dataset=to_name,
                    to_column=to_column,
                    kind=kind,
                    confidence=confidence,
                    overlap=overlap,
                    orphan_rate=orphan_rate,
                    reason=reason,
                    is_safe_join=orphan_rate <= ORPHAN_WARNING,
                )
            )
    return results


def _drop_mirrors(relationships: list[Relationship]) -> list[Relationship]:
    """Keep one direction of each pair -- the one pointing at the key side."""
    kept: list[Relationship] = []
    seen: set[frozenset] = set()
    for rel in relationships:
        signature = frozenset(
            {(rel.from_dataset, rel.from_column), (rel.to_dataset, rel.to_column)}
        )
        if signature in seen:
            continue
        seen.add(signature)
        kept.append(rel)
    return kept

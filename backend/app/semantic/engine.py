"""Semantic engine: decide what each uploaded column actually represents.

Scoring combines four signals (PRD sec. 12):

1. the column name against each concept's synonym list (exact, normalised, token
   overlap, then substring);
2. the column's dtype against the concept's role -- a measure must be numeric, a
   temporal concept must parse as dates;
3. the values themselves -- cardinality, magnitude and shape;
4. what the user has already confirmed for this business (``MappingMemory``),
   which outranks everything else.

A column is never mapped on name alone: a numeric-looking ``salary`` column full
of text is rejected, and anything below the medium threshold is returned for the
user to confirm rather than silently guessed (PRD sec. 14).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from app.semantic.concepts import CONCEPTS, ENTITY_SIGNALS, Concept, Role

HIGH_THRESHOLD = 0.75
MEDIUM_THRESHOLD = 0.50

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def normalize(name: str) -> str:
    """``Monthly Pay (INR)`` -> ``monthly_pay_inr``."""
    return "_".join(t for t in _TOKEN_SPLIT.split(str(name).strip().lower()) if t)


def tokens(name: str) -> set[str]:
    return {t for t in _TOKEN_SPLIT.split(str(name).strip().lower()) if t}


@dataclass
class ColumnSignals:
    """Everything the engine knows about one column, from the profiler."""

    name: str
    dtype: str
    non_null: int
    unique: int
    total: int
    numeric_share: float = 0.0
    date_share: float = 0.0
    mean: float | None = None
    max_value: float | None = None
    min_value: float | None = None

    @property
    def unique_ratio(self) -> float:
        return self.unique / self.non_null if self.non_null else 0.0


@dataclass
class MappingProposal:
    source_column: str
    concept: str | None
    score: float
    confidence: str
    rationale: str
    alternatives: list[tuple[str, float]]

    @property
    def needs_confirmation(self) -> bool:
        return self.confidence != "high"


# A weak synonym can never on its own exceed the confirmation threshold.
WEAK_SYNONYM_CEILING = 0.62


def _name_score(col_norm: str, col_tokens: set[str], c: Concept) -> tuple[float, str]:
    """Match the column name against a concept's vocabulary."""
    best, why = 0.0, ""
    if col_norm == c.name.lower():
        return 1.0, f"column name equals concept {c.name}"
    for syn in c.synonyms:
        syn_norm = normalize(syn)
        if col_norm == syn_norm:
            return 1.0, f"exact name match on '{syn}'"
        syn_tokens = tokens(syn)
        if syn_tokens and syn_tokens <= col_tokens:
            # "monthly_salary_inr" contains all of "salary"
            score = 0.85 * len(syn_tokens) / max(len(col_tokens), 1) + 0.15
            if score > best:
                best, why = min(score, 0.95), f"name contains '{syn}'"
        elif col_tokens and col_tokens <= syn_tokens:
            score = 0.7
            if score > best:
                best, why = score, f"name is part of '{syn}'"
        elif len(syn_norm) >= 4 and syn_norm in col_norm:
            score = 0.6
            if score > best:
                best, why = score, f"name resembles '{syn}'"

    # Generic words only get the column as far as "please confirm".
    for weak in c.weak_synonyms:
        weak_norm = normalize(weak)
        if col_norm == weak_norm or weak_norm in col_tokens:
            score = WEAK_SYNONYM_CEILING
            if score > best:
                best, why = score, f"'{weak}' is a generic name that often means {c.label}"
    return best, why


def _type_multiplier(sig: ColumnSignals, c: Concept) -> tuple[float, str]:
    """Reject or discount a concept whose expected type the data contradicts."""
    if c.role is Role.MEASURE:
        if sig.numeric_share >= 0.9:
            return 1.0, "values are numeric"
        if sig.numeric_share >= 0.6:
            return 0.6, "values are mostly numeric"
        return 0.0, "values are not numeric"
    if c.role is Role.TEMPORAL:
        if sig.date_share >= 0.8:
            return 1.0, "values parse as dates"
        if sig.date_share >= 0.5:
            return 0.6, "values partly parse as dates"
        return 0.0, "values do not parse as dates"
    if c.role is Role.IDENTIFIER:
        # Identifiers are high-cardinality; a 3-value column is not an employee id.
        if sig.unique_ratio >= 0.9:
            return 1.0, "values are nearly unique"
        if sig.unique_ratio >= 0.3:
            return 0.8, "values are moderately unique"
        return 0.45, "values repeat heavily for an identifier"
    # Dimension: low cardinality is the expectation.
    if sig.unique_ratio <= 0.2 or sig.unique <= 50:
        return 1.0, "small set of repeated values"
    if sig.unique_ratio <= 0.5:
        return 0.75, "moderate number of distinct values"
    return 0.5, "values are almost all distinct for a dimension"


def _value_bonus(sig: ColumnSignals, c: Concept) -> float:
    """Small nudges from value magnitude for measures that overlap by name."""
    if c.role is not Role.MEASURE or sig.mean is None:
        return 0.0
    if c.name == "EMPLOYEE_COMPENSATION" and 3_000 <= sig.mean <= 5_000_000:
        return 0.05
    if c.name == "RATING" and sig.max_value is not None and sig.max_value <= 10:
        return 0.08
    if c.name == "QUANTITY" and sig.max_value is not None and sig.max_value <= 1_000:
        return 0.04
    if c.name in {"REVENUE", "COGS", "OPERATING_EXPENSE"} and sig.mean >= 50:
        return 0.03
    return 0.0


def _confidence(score: float) -> str:
    if score >= HIGH_THRESHOLD:
        return "high"
    if score >= MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def score_column(
    sig: ColumnSignals, entity_kind: str = "unknown", memory: dict[str, str | None] | None = None
) -> MappingProposal:
    """Rank every concept for one column and return the best proposal."""
    col_norm = normalize(sig.name)
    col_tokens = tokens(sig.name)

    if memory and col_norm in memory:
        remembered = memory[col_norm]
        return MappingProposal(
            source_column=sig.name,
            concept=remembered,
            score=1.0,
            confidence="high",
            rationale="previously confirmed by a user for this business",
            alternatives=[],
        )

    scored: list[tuple[str, float, str]] = []
    for name, c in CONCEPTS.items():
        name_score, why = _name_score(col_norm, col_tokens, c)
        if name_score <= 0:
            continue
        type_mult, type_why = _type_multiplier(sig, c)
        if type_mult <= 0:
            continue
        score = name_score * type_mult + _value_bonus(sig, c)
        # Concepts belonging to a different kind of dataset are plausible but weaker.
        if c.entity_hints and entity_kind != "unknown" and entity_kind not in c.entity_hints:
            score *= 0.7
        scored.append((name, min(score, 1.0), f"{why}; {type_why}"))

    if not scored:
        return MappingProposal(sig.name, None, 0.0, "low", "no concept matched this column", [])

    scored.sort(key=lambda row: row[1], reverse=True)
    best_name, best_score, rationale = scored[0]

    # Two concepts within a whisker of each other is ambiguity, not confidence.
    if len(scored) > 1 and best_score - scored[1][1] < 0.05 and best_score >= HIGH_THRESHOLD:
        best_score = MEDIUM_THRESHOLD + 0.15
        rationale += f"; ambiguous against {scored[1][0]}"

    return MappingProposal(
        source_column=sig.name,
        concept=best_name,
        score=round(best_score, 3),
        confidence=_confidence(best_score),
        rationale=rationale,
        alternatives=[(n, round(s, 3)) for n, s, _ in scored[1:4]],
    )


def detect_entity_kind(proposals: list[MappingProposal]) -> str:
    """Classify the dataset from the concepts its columns matched."""
    found = {p.concept for p in proposals if p.concept and p.score >= MEDIUM_THRESHOLD}
    best_kind, best_hits = "unknown", 0
    for kind, signals in ENTITY_SIGNALS.items():
        hits = len(found & set(signals))
        if hits > best_hits:
            best_kind, best_hits = kind, hits
    return best_kind if best_hits >= 2 else "unknown"


def map_dataframe(
    df: pd.DataFrame, signals: list[ColumnSignals], memory: dict[str, str | None] | None = None
) -> tuple[str, list[MappingProposal]]:
    """Map every column, then re-run once the dataset kind is known.

    The second pass matters: ``amount`` in an expense file should not win
    ``REVENUE`` just because that concept lists more synonyms.
    """
    first = [score_column(s, "unknown", memory) for s in signals]
    kind = detect_entity_kind(first)
    if kind == "unknown":
        return kind, _resolve_duplicates(first)
    second = [score_column(s, kind, memory) for s in signals]
    return kind, _resolve_duplicates(second)


def _resolve_duplicates(proposals: list[MappingProposal]) -> list[MappingProposal]:
    """One concept, one column: the strongest claim wins, the rest ask the user.

    Measures are exempt -- ``basic_pay`` and ``gross_pay`` may both legitimately
    be compensation, and the analytics engine sums them.
    """
    by_concept: dict[str, list[MappingProposal]] = {}
    for p in proposals:
        if p.concept:
            by_concept.setdefault(p.concept, []).append(p)

    for concept_name, group in by_concept.items():
        if len(group) < 2 or CONCEPTS[concept_name].role is Role.MEASURE:
            continue
        group.sort(key=lambda p: p.score, reverse=True)
        for loser in group[1:]:
            loser.alternatives = [(concept_name, loser.score), *loser.alternatives][:4]
            loser.concept = None
            loser.score = 0.0
            loser.confidence = "low"
            loser.rationale = (
                f"'{group[0].source_column}' is a stronger match for {concept_name}"
            )
    return proposals

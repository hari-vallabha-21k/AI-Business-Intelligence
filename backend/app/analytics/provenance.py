"""Provenance and metric caveats (PRD sec. 29, sec. 18).

Two questions about every number on screen:

* where did it come from -- which file, which version, which period;
* what is wrong with it -- incomplete inputs, unconfirmed column meanings, rows
  that could not be attributed to a branch.

Both are derived from the dataset versions that actually fed the calculation, so
a figure can always be traced back to the upload behind it (Rule 10).
"""

from __future__ import annotations

import pandas as pd

from app.analytics.registry import METRICS, METRICS_BY_KEY, Metric
from app.models import DatasetVersion

# Share of rows missing a branch before it is worth mentioning.
UNATTRIBUTED_WARNING = 0.02


def _required_concepts(metric: Metric, seen: set[str] | None = None) -> set[tuple[str, str]]:
    """Every (entity kind, concept) this metric needs, including via dependencies."""
    seen = seen or set()
    if metric.key in seen:
        return set()
    seen.add(metric.key)

    needed = set(metric.requires)
    for group in metric.requires_any:
        needed |= set(group)
    for dep in metric.depends_on:
        if dep in METRICS_BY_KEY:
            needed |= _required_concepts(METRICS_BY_KEY[dep], seen)
    return needed


def _version_concepts(version: DatasetVersion) -> set[str]:
    return {m.concept for m in version.mappings if m.concept}


def _unconfirmed_concepts(version: DatasetVersion) -> set[str]:
    return {
        m.concept
        for m in version.mappings
        if m.concept and m.needs_confirmation and not m.confirmed_by_user
    }


def build(
    versions: list[DatasetVersion], frames: dict[str, pd.DataFrame]
) -> tuple[dict[str, list[str]], dict[str, list[dict]]]:
    """Return (caveats per metric, provenance rows per metric).

    A caveat prefixed ``CONFIRM:`` downgrades the metric to NEEDS_CONFIRMATION
    rather than merely annotating it -- the number rests on a guess the user has
    not agreed to.
    """
    caveats: dict[str, list[str]] = {}
    sources: dict[str, list[dict]] = {}

    # Caveats that apply to everything drawn from a given entity kind.
    kind_caveats: dict[str, list[str]] = {}
    for version in versions:
        kind = version.entity_kind.value
        if version.grain.get("is_ambiguous", False):
            kind_caveats.setdefault(kind, []).append(
                f"'{version.filename}' has no reliable row identifier, so its totals may "
                "include repeated rows."
            )
        duplicates = version.grain.get("duplicate_rows", 0)
        if duplicates:
            kind_caveats.setdefault(kind, []).append(
                f"'{version.filename}' contains {duplicates:,} rows that repeat an "
                "identifier that should be unique."
            )
        classification = version.classification or {}
        if classification.get("needs_review"):
            kind_caveats.setdefault(kind, []).append(
                f"CONFIRM:we are only {classification.get('confidence', 0):.0%} confident "
                f"that '{version.filename}' is "
                f"{str(classification.get('category', 'this')).replace('_', ' ')} data."
            )

    for kind, frame in frames.items():
        if "BRANCH" in frame.columns and len(frame):
            missing = float(frame["BRANCH"].isna().mean())
            if missing > UNATTRIBUTED_WARNING:
                kind_caveats.setdefault(kind, []).append(
                    f"{missing:.1%} of rows have no branch, so branch figures do not add "
                    "up to the company total."
                )

    for metric in METRICS:
        needed = _required_concepts(metric)
        metric_caveats: list[str] = []
        metric_sources: list[dict] = []

        for entity_kind, concept in sorted(needed):
            for version in versions:
                if version.entity_kind.value != entity_kind:
                    continue
                if concept not in _version_concepts(version):
                    continue
                metric_sources.append(
                    {
                        "concept": concept,
                        "dataset": version.dataset.name,
                        "file": version.filename,
                        "version": version.version,
                        "rows": version.row_count,
                        "period_start": version.period_start.isoformat()
                        if version.period_start
                        else None,
                        "period_end": version.period_end.isoformat()
                        if version.period_end
                        else None,
                        "grain": version.grain.get("description"),
                    }
                )
                if concept in _unconfirmed_concepts(version):
                    column = next(
                        (m.source_column for m in version.mappings if m.concept == concept), concept
                    )
                    metric_caveats.append(
                        f"CONFIRM:we are not certain that '{column}' in "
                        f"'{version.filename}' means {concept.replace('_', ' ').lower()}."
                    )

            if any(source["concept"] == concept for source in metric_sources):
                metric_caveats.extend(kind_caveats.get(entity_kind, []))

        if metric_caveats:
            caveats[metric.key] = sorted(set(metric_caveats))
        if metric_sources:
            # One row per (concept, file); duplicates arise when a concept comes
            # from several files, which is information worth keeping.
            sources[metric.key] = metric_sources

    return caveats, sources

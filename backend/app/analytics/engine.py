"""Analytics engine: turn canonical records into metrics with evidence.

Metrics are resolved in dependency order. A metric whose inputs are absent is
not skipped silently -- it is returned as unavailable with the reason traced
back to the concept that is actually missing, which is what the readiness panel
and the "why can't I see profit?" answer are built from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from app.analytics.registry import METRICS, METRICS_BY_KEY, Frames, Metric

ENTITY_KINDS = ("sales", "employee", "expense")


class Availability(str, Enum):
    """How far a metric can be trusted (PRD sec. 18).

    The distinction that matters is between "we cannot compute this" and "we
    computed it from incomplete data" -- the second produces a number, and a
    number without its caveat is worse than no number.
    """

    AVAILABLE = "AVAILABLE"
    PARTIALLY_AVAILABLE = "PARTIALLY_AVAILABLE"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class MetricResult:
    key: str
    label: str
    unit: str
    value: float | None
    availability: Availability
    formula: str
    reason: str | None = None
    inputs: dict[str, float] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)
    provenance: list[dict] = field(default_factory=list)

    @property
    def available(self) -> bool:
        """A value exists. Callers that must not use a caveated number should
        check ``availability`` instead."""
        return self.value is not None

    @property
    def is_trustworthy(self) -> bool:
        return self.availability is Availability.AVAILABLE

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "unit": self.unit,
            "value": None if self.value is None else round(self.value, 4),
            "available": self.available,
            "availability": self.availability.value,
            "formula": self.formula,
            "reason": self.reason,
            "caveats": self.caveats,
            "inputs": {k: round(v, 4) for k, v in self.inputs.items()},
            "provenance": self.provenance,
        }


def available_concepts(frames: Frames) -> dict[str, set[str]]:
    """Which concepts actually carry usable values, per entity kind."""
    out: dict[str, set[str]] = {}
    for kind in ENTITY_KINDS:
        df = frames.get(kind)
        if df is None or df.empty:
            out[kind] = set()
            continue
        # A column present but entirely null supports nothing.
        out[kind] = {str(c) for c in df.columns if df[c].notna().any()}
    return out


def _order_metrics() -> list[Metric]:
    """Topologically order the registry so dependencies compute first."""
    ordered: list[Metric] = []
    seen: set[str] = set()

    def visit(metric: Metric, stack: frozenset[str]) -> None:
        if metric.key in seen or metric.key in stack:
            return
        for dep in metric.depends_on:
            if dep in METRICS_BY_KEY:
                visit(METRICS_BY_KEY[dep], stack | {metric.key})
        seen.add(metric.key)
        ordered.append(metric)

    for metric in METRICS:
        visit(metric, frozenset())
    return ordered


_ORDERED = _order_metrics()


def resolve_availability(available: dict[str, set[str]]) -> dict[str, str | None]:
    """Per metric, ``None`` if it can be computed or the reason it cannot.

    Both the metric values and the readiness panel derive from this one pass, so
    a metric can never be listed as available in one place and unavailable in
    the other.
    """
    reasons: dict[str, str | None] = {}
    for metric in _ORDERED:
        missing = metric.missing_requirements(available)
        reason = metric.explain_missing(missing) if missing else None
        if reason is None:
            # Trace an unavailable dependency back to its own root cause.
            for dep in metric.depends_on:
                dep_reason = reasons.get(dep, f"{dep} was not evaluated")
                if dep_reason is not None:
                    dep_label = METRICS_BY_KEY[dep].label if dep in METRICS_BY_KEY else dep
                    reason = (
                        f"{metric.label} needs {dep_label}, which is unavailable. {dep_reason}"
                    ).strip()
                    break
        reasons[metric.key] = reason
    return reasons


def evaluate(
    frames: Frames,
    keys: list[str] | None = None,
    quality: dict[str, list[str]] | None = None,
    sources: dict[str, list[dict]] | None = None,
) -> dict[str, MetricResult]:
    """Compute every metric the data supports over the given frames.

    ``quality`` carries per-metric caveats (incomplete inputs, unconfirmed
    mappings); ``sources`` carries provenance rows. Both are supplied by the
    layer that knows where the frames came from, so this module stays a pure
    calculator.
    """
    available = available_concepts(frames)
    reasons = resolve_availability(available)
    computed: dict[str, float] = {}
    results: dict[str, MetricResult] = {}

    def unavailable(metric: Metric, reason: str) -> MetricResult:
        return MetricResult(
            key=metric.key,
            label=metric.label,
            unit=metric.unit,
            value=None,
            availability=Availability.UNAVAILABLE,
            formula=metric.formula,
            reason=reason,
        )

    for metric in _ORDERED:
        reason = reasons[metric.key]
        if reason is not None:
            results[metric.key] = unavailable(metric, reason)
            continue

        try:
            value = metric.fn(frames, computed)
        except Exception:  # noqa: BLE001 - a bad metric must not sink the request
            value = None

        # A metric can still fail on the values themselves: an empty mean, or a
        # ratio whose denominator turns out to be zero.
        if value is None or pd.isna(value) or value in (float("inf"), float("-inf")):
            results[metric.key] = unavailable(
                metric,
                f"{metric.label} could not be calculated from the available values.",
            )
            continue

        value = float(value)
        computed[metric.key] = value

        # A computed value is not automatically a trustworthy one: it may rest
        # on caveated inputs, unconfirmed column meanings or incomplete data.
        caveats = list(quality.get(metric.key, [])) if quality else []
        for dep in metric.depends_on:
            dep_result = results.get(dep)
            if dep_result is not None:
                caveats.extend(dep_result.caveats)

        availability = Availability.AVAILABLE
        if any(c.startswith("CONFIRM:") for c in caveats):
            availability = Availability.NEEDS_CONFIRMATION
        elif caveats:
            availability = Availability.PARTIALLY_AVAILABLE

        results[metric.key] = MetricResult(
            key=metric.key,
            label=metric.label,
            unit=metric.unit,
            value=value,
            availability=availability,
            formula=metric.formula,
            inputs={dep: computed[dep] for dep in metric.depends_on if dep in computed},
            caveats=sorted(set(c.removeprefix("CONFIRM:") for c in caveats)),
            provenance=list(sources.get(metric.key, [])) if sources else [],
        )

    if keys:
        return {k: results[k] for k in keys if k in results}
    return results


def split_by(frames: Frames, concept: str) -> dict[str, Frames]:
    """Partition every frame by a dimension, e.g. BRANCH or DEPARTMENT.

    Frames lacking the dimension are dropped from each slice rather than
    duplicated -- attributing every branch the company's whole expense sheet
    would silently invent costs.
    """
    values: set[str] = set()
    for df in frames.values():
        if df is not None and concept in df.columns:
            values |= {str(v) for v in df[concept].dropna().unique()}

    out: dict[str, Frames] = {}
    for value in sorted(values):
        slice_frames: Frames = {}
        for kind, df in frames.items():
            if df is None or concept not in df.columns:
                continue
            subset = df[df[concept].astype(str) == value]
            if not subset.empty:
                slice_frames[kind] = subset.reset_index(drop=True)
        out[value] = slice_frames
    return out

"""Comparison engine: branch vs branch, period vs period (PRD sec. 17, 19).

Rankings are only produced from metrics that are available for every entity
being compared -- ranking three branches on profit when one lacks cost data
would put a branch on top for having less data.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analytics.engine import Frames, MetricResult, evaluate, split_by
from app.analytics.registry import METRICS_BY_KEY


@dataclass
class Change:
    key: str
    label: str
    unit: str
    current: float | None
    previous: float | None
    absolute: float | None
    percent: float | None
    direction: str  # up | down | flat | unknown
    higher_is_better: bool | None

    @property
    def is_favourable(self) -> bool | None:
        if self.higher_is_better is None or self.direction in {"flat", "unknown"}:
            return None
        return (self.direction == "up") == self.higher_is_better

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "unit": self.unit,
            "current": self.current,
            "previous": self.previous,
            "absolute": self.absolute,
            "percent": None if self.percent is None else round(self.percent, 2),
            "direction": self.direction,
            "favourable": self.is_favourable,
        }


def compare_metrics(
    current: dict[str, MetricResult], previous: dict[str, MetricResult]
) -> list[Change]:
    """Period-over-period change for every metric available in both sets."""
    changes: list[Change] = []
    for key, cur in current.items():
        prev = previous.get(key)
        if not cur.available or prev is None or not prev.available:
            continue
        cur_v, prev_v = cur.value, prev.value
        if cur_v is None or prev_v is None:
            continue
        absolute = cur_v - prev_v
        percent = None if prev_v == 0 else 100 * absolute / abs(prev_v)
        if abs(absolute) < 1e-9:
            direction = "flat"
        else:
            direction = "up" if absolute > 0 else "down"
        changes.append(
            Change(
                key=key,
                label=cur.label,
                unit=cur.unit,
                current=cur_v,
                previous=prev_v,
                absolute=absolute,
                percent=percent,
                direction=direction,
                higher_is_better=METRICS_BY_KEY[key].higher_is_better
                if key in METRICS_BY_KEY
                else None,
            )
        )
    return changes


def compare_dimension(frames: Frames, concept: str = "BRANCH") -> dict:
    """Evaluate every slice of a dimension and rank the comparable metrics."""
    slices = split_by(frames, concept)
    per_slice = {name: evaluate(sub) for name, sub in slices.items()}

    metric_keys: list[str] = []
    for results in per_slice.values():
        for key, res in results.items():
            if res.available and key not in metric_keys:
                metric_keys.append(key)

    rows = []
    for key in metric_keys:
        values = {name: res[key].value for name, res in per_slice.items() if res[key].available}
        # Only rank when every slice can supply the metric.
        comparable = len(values) == len(per_slice) and len(values) > 1
        meta = METRICS_BY_KEY.get(key)
        ranking = None
        note = None
        if not comparable:
            note = (
                "Not comparable: this metric is unavailable for at least one "
                f"{concept.lower()}."
            )
        elif meta and meta.higher_is_better is None:
            note = "No better or worse direction for this metric."
        elif meta and not meta.rankable:
            note = (
                "Shown for reference only: this is an absolute total, so the "
                f"smallest {concept.lower()} will always be lowest. Compare the "
                "ratio instead."
            )
        elif meta:
            ranking = sorted(
                values, key=lambda n: values[n], reverse=bool(meta.higher_is_better)
            )
        rows.append(
            {
                "key": key,
                "label": meta.label if meta else key,
                "unit": meta.unit if meta else "",
                "values": values,
                "comparable": comparable,
                "ranking": ranking,
                "best": ranking[0] if ranking else None,
                "worst": ranking[-1] if ranking else None,
                "note": note,
            }
        )

    return {
        "dimension": concept,
        "members": sorted(per_slice),
        "metrics": rows,
        "detail": {name: {k: r.as_dict() for k, r in res.items()} for name, res in per_slice.items()},
    }


def rank_members(comparison: dict, key: str) -> list[str] | None:
    for row in comparison["metrics"]:
        if row["key"] == key:
            return row["ranking"]
    return None

"""Data quality engine (PRD sec. 10) and analysis readiness (process doc sec. 7).

Two distinct jobs:

* ``assess_file`` grades one upload -- critical issues block ingestion, warnings
  and info notes are recorded and shown.
* ``readiness`` answers the question the user actually cares about: given what
  has been uploaded, which analyses can run and which cannot, and why.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from app.semantic.concepts import label
from app.semantic.engine import MappingProposal

MISSING_WARN_PCT = 20.0


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    column_name: str | None = None
    details: dict | None = None

    def as_dict(self) -> dict:
        data = asdict(self)
        data["details"] = data["details"] or {}
        return data


def assess_file(
    df: pd.DataFrame, profile: dict, proposals: list[MappingProposal], entity_kind: str
) -> list[Issue]:
    issues: list[Issue] = []
    mapped = {p.concept for p in proposals if p.concept}

    if profile["row_count"] == 0:
        issues.append(Issue("critical", "empty_file", "This file contains no data rows."))
        return issues

    if entity_kind == "unknown":
        # Not fatal: the file is kept and the user is asked what the columns mean.
        # Once they confirm, the kind is recomputed and the data becomes active.
        issues.append(
            Issue(
                "warning",
                "unknown_entity",
                "We couldn't tell whether this file describes sales, employees or "
                "expenses. Confirm what the columns below mean and it will be included "
                "in your analysis.",
            )
        )

    if "BRANCH" not in mapped:
        issues.append(
            Issue(
                "warning",
                "missing_branch",
                "No branch column was found, so these rows can't be compared across branches. "
                "They will be attributed to the branch chosen at upload.",
            )
        )
    if "DATE" not in mapped:
        issues.append(
            Issue(
                "warning",
                "missing_date",
                "No date column was found. Historical comparison needs the reporting period "
                "you set for this upload.",
            )
        )

    if entity_kind == "sales" and "REVENUE" not in mapped:
        issues.append(
            Issue("warning", "missing_revenue",
                  "This looks like a sales file but no revenue amount could be identified. "
                  "Confirm which column holds the sale value.")
        )
    if entity_kind == "employee" and "EMPLOYEE_COMPENSATION" not in mapped:
        issues.append(
            Issue("warning", "missing_salary",
                  "No salary column was identified, so employee cost cannot be calculated.")
        )

    duplicates = profile.get("duplicate_rows", 0)
    if duplicates:
        issues.append(
            Issue(
                "warning",
                "duplicate_rows",
                f"{duplicates:,} rows are exact duplicates of another row.",
                details={"count": duplicates},
            )
        )

    for col in profile["columns"]:
        if col["missing_pct"] >= MISSING_WARN_PCT:
            issues.append(
                Issue(
                    "warning",
                    "missing_values",
                    f"'{col['name']}' is empty in {col['missing_pct']:.0f}% of rows.",
                    column_name=col["name"],
                    details={"missing_pct": col["missing_pct"]},
                )
            )

    for p in proposals:
        if p.concept is None:
            issues.append(
                Issue(
                    "info",
                    "unmapped_column",
                    f"We couldn't determine what '{p.source_column}' represents. "
                    "It will be ignored until you map it.",
                    column_name=p.source_column,
                )
            )
        elif p.needs_confirmation:
            issues.append(
                Issue(
                    "info",
                    "low_confidence_mapping",
                    f"'{p.source_column}' looks like {label(p.concept)}, but we're not certain. "
                    "Please confirm.",
                    column_name=p.source_column,
                    details={"concept": p.concept, "confidence": p.confidence},
                )
            )

    # Negative money is legitimate (refunds), but negative pay is a data error.
    for p in proposals:
        if p.concept in {"EMPLOYEE_COMPENSATION", "QUANTITY"} and p.source_column in df.columns:
            values = pd.to_numeric(df[p.source_column], errors="coerce")
            bad = int((values < 0).sum())
            if bad:
                issues.append(
                    Issue(
                        "warning",
                        "negative_values",
                        f"'{p.source_column}' has {bad:,} negative values, "
                        f"which is unexpected for {label(p.concept)}.",
                        column_name=p.source_column,
                        details={"count": bad},
                    )
                )

    return issues


def readiness(available: dict[str, set[str]]) -> list[dict]:
    """Which analyses the uploaded data supports, and what each one still needs.

    ``available`` maps entity kind -> concepts present for that kind.
    """
    from app.analytics.engine import resolve_availability
    from app.analytics.registry import METRICS_BY_KEY

    reasons = resolve_availability(available)
    return [
        {
            "metric": key,
            "label": METRICS_BY_KEY[key].label,
            "available": reason is None,
            "reason": reason,
        }
        for key, reason in reasons.items()
    ]

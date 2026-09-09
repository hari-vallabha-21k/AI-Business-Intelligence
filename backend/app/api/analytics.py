"""Analytics routes: overview, branch comparison, periods, problems."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.analytics.comparison import compare_dimension, compare_metrics
from app.analytics.engine import available_concepts, evaluate, split_by
from app.analytics.problems import (
    MATERIAL_PCT,
    contribution_analysis,
    detect_branch_problems,
    detect_period_problems,
)
from app.analytics.registry import HEADLINE_METRICS
from app.api.deps import get_owned_business
from app.db import get_db
from app.models import Business
from app.services.layer import load_frames, load_scoped
from app.services.quality import readiness

router = APIRouter(prefix="/api/businesses/{business_id}", tags=["analytics"])

BranchFilter = Query(None, description="Branch names; omit for all branches")

# How many movements are decomposed by branch in one period comparison.
MAX_DRIVER_METRICS = 6


def _scoped_frames(
    db: Session,
    business: Business,
    branches: list[str] | None,
    period_start: date | None,
    period_end: date | None,
):
    frames, notes = load_scoped(db, business.id, branches, period_start, period_end)
    if not frames:
        raise HTTPException(
            status_code=404,
            detail="No data is available for this selection. Upload a file or widen the period."
            + (" " + " ".join(notes) if notes else ""),
        )
    return frames, notes


@router.get("/overview")
def overview(
    branches: list[str] | None = BranchFilter,
    period_start: date | None = None,
    period_end: date | None = None,
    business: Business = Depends(get_owned_business),
    db: Session = Depends(get_db),
) -> dict:
    """Company-wide KPIs plus what the data cannot yet answer (PRD sec. 18)."""
    frames, notes = _scoped_frames(db, business, branches, period_start, period_end)
    results = evaluate(frames)
    concepts = available_concepts(frames)

    return {
        "business": {"id": business.id, "name": business.name, "currency": business.currency},
        "scope": {
            "branches": branches or sorted(split_by(frames, "BRANCH")),
            "period_start": period_start,
            "period_end": period_end,
        },
        "headline": [
            results[k].as_dict() for k in HEADLINE_METRICS if k in results
        ],
        "metrics": {k: r.as_dict() for k, r in results.items()},
        "unavailable": [r.as_dict() for r in results.values() if not r.available],
        "readiness": readiness(concepts),
        "notes": notes,
        "row_counts": {kind: len(df) for kind, df in frames.items()},
    }


@router.get("/compare/branches")
def compare_branches(
    period_start: date | None = None,
    period_end: date | None = None,
    business: Business = Depends(get_owned_business),
    db: Session = Depends(get_db),
) -> dict:
    """Rank every branch on the metrics all of them can supply (PRD sec. 17)."""
    frames, notes = _scoped_frames(db, business, None, period_start, period_end)
    comparison = compare_dimension(frames, "BRANCH")
    comparison["notes"] = notes
    if len(comparison["members"]) < 2:
        comparison["note"] = "Branch comparison needs at least two branches with data."
    comparison["findings"] = [f.as_dict() for f in detect_branch_problems(comparison)]
    return comparison


@router.get("/compare/dimension")
def compare_by_dimension(
    concept: str = Query("DEPARTMENT", description="BRANCH, DEPARTMENT, ROLE, CATEGORY..."),
    period_start: date | None = None,
    period_end: date | None = None,
    business: Business = Depends(get_owned_business),
    db: Session = Depends(get_db),
) -> dict:
    from app.semantic.concepts import CONCEPTS

    if concept not in CONCEPTS:
        raise HTTPException(status_code=422, detail=f"Unknown concept '{concept}'.")
    frames, _ = _scoped_frames(db, business, None, period_start, period_end)
    return compare_dimension(frames, concept)


@router.get("/compare/periods")
def compare_periods(
    current_start: date,
    current_end: date,
    previous_start: date,
    previous_end: date,
    branches: list[str] | None = BranchFilter,
    business: Business = Depends(get_owned_business),
    db: Session = Depends(get_db),
) -> dict:
    """Period over period, with findings and branch-level contribution."""
    current_frames, notes = _scoped_frames(db, business, branches, current_start, current_end)
    previous_frames = load_frames(db, business.id, branches, previous_start, previous_end)
    if not previous_frames:
        raise HTTPException(
            status_code=404, detail="No data is available for the comparison period."
        )

    current = evaluate(current_frames)
    previous = evaluate(previous_frames)
    changes = compare_metrics(current, previous)
    findings = detect_period_problems(changes)

    # Decompose the movements that moved, by branch.
    current_by_branch = {n: evaluate(f) for n, f in split_by(current_frames, "BRANCH").items()}
    previous_by_branch = {n: evaluate(f) for n, f in split_by(previous_frames, "BRANCH").items()}
    # Decompose only the movements that are both material and additive, largest
    # first, so the answer is a short list of real drivers rather than one line
    # per metric in the registry.
    material = sorted(
        (c for c in changes if c.percent is not None and abs(c.percent) >= MATERIAL_PCT),
        key=lambda c: abs(c.percent),
        reverse=True,
    )
    drivers = []
    for change in material[:MAX_DRIVER_METRICS]:
        drivers.extend(
            f.as_dict()
            for f in contribution_analysis(current_by_branch, previous_by_branch, change.key)
        )

    return {
        "current": {"start": current_start, "end": current_end,
                    "metrics": {k: r.as_dict() for k, r in current.items()}},
        "previous": {"start": previous_start, "end": previous_end,
                     "metrics": {k: r.as_dict() for k, r in previous.items()}},
        "notes": notes,
        "changes": [c.as_dict() for c in changes],
        "findings": [f.as_dict() for f in findings],
        "drivers": drivers,
    }


@router.get("/problems")
def problems(
    period_start: date | None = None,
    period_end: date | None = None,
    business: Business = Depends(get_owned_business),
    db: Session = Depends(get_db),
) -> dict:
    """Everything currently worth the owner's attention, in one list."""
    frames, notes = _scoped_frames(db, business, None, period_start, period_end)
    comparison = compare_dimension(frames, "BRANCH")
    findings = [f.as_dict() for f in detect_branch_problems(comparison)]
    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))
    return {"findings": findings, "branches": comparison["members"], "notes": notes}

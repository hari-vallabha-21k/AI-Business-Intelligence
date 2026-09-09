"""Analytics routes: overview, branch comparison, periods, problems."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
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
from app.models import Business, Dataset, DatasetRelationship, DatasetVersion, Entity
from app.qa import pipeline as qa
from app.schemas import AskRequest
from app.analytics.provenance import build as build_provenance
from app.services.layer import load_data, load_frames
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
    loaded = load_data(db, business.id, branches, period_start, period_end)
    if not loaded.frames:
        raise HTTPException(
            status_code=404,
            detail="No data is available for this selection. Upload a file or widen the period."
            + (" " + " ".join(loaded.notes) if loaded.notes else ""),
        )
    return loaded


@router.get("/overview")
def overview(
    branches: list[str] | None = BranchFilter,
    period_start: date | None = None,
    period_end: date | None = None,
    business: Business = Depends(get_owned_business),
    db: Session = Depends(get_db),
) -> dict:
    """Company-wide KPIs plus what the data cannot yet answer (PRD sec. 18)."""
    loaded = _scoped_frames(db, business, branches, period_start, period_end)
    frames, notes = loaded.frames, loaded.notes
    # Metrics are calculated on the frames; their trustworthiness and lineage
    # come from the dataset versions behind those frames.
    quality, sources = build_provenance(loaded.versions, frames)
    results = evaluate(frames, quality=quality, sources=sources)
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
        "caveated": [
            r.as_dict() for r in results.values() if r.available and not r.is_trustworthy
        ],
        "sources": sorted(
            {
                (v.dataset.name, v.filename, v.version)
                for v in loaded.versions
            }
        ),
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
    loaded = _scoped_frames(db, business, None, period_start, period_end)
    frames, notes = loaded.frames, loaded.notes
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
    return compare_dimension(
        _scoped_frames(db, business, None, period_start, period_end).frames, concept
    )


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
    loaded = _scoped_frames(db, business, branches, current_start, current_end)
    current_frames, notes = loaded.frames, loaded.notes
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


@router.post("/ask")
def ask(
    payload: AskRequest,
    business: Business = Depends(get_owned_business),
    db: Session = Depends(get_db),
) -> dict:
    """Answer a question in natural language (PRD sec. 28).

    Intent, scope and metric resolution are deterministic; the calculation is
    deterministic; only the closing explanation is written by a model, and only
    from evidence this endpoint already validated.
    """
    if not payload.question.strip():
        raise HTTPException(status_code=422, detail="Please type a question.")
    return qa.answer(db, business, payload.question.strip()).as_dict()


@router.get("/model")
def semantic_model(
    business: Business = Depends(get_owned_business), db: Session = Depends(get_db)
) -> dict:
    """What the system understands about this business (PRD sec. 17).

    Only what the uploaded data actually supports -- no assumed departments,
    products or customers.
    """
    loaded = load_data(db, business.id)
    # Every dataset is listed, including reference tables that are never summed:
    # the user needs to see what the system holds, not only what it aggregates.
    all_versions = db.scalars(
        select(DatasetVersion)
        .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
        .where(
            Dataset.business_id == business.id,
            DatasetVersion.superseded_by_id.is_(None),
        )
    ).all()
    datasets = [
        {
            "dataset": version.dataset.name,
            "file": version.filename,
            "version": version.version,
            "classification": version.classification,
            "grain": version.grain,
            "rows": version.row_count,
            "period_start": version.period_start,
            "period_end": version.period_end,
        }
        for version in all_versions
    ]
    entities = db.scalars(select(Entity).where(Entity.business_id == business.id)).all()
    relationships = db.scalars(
        select(DatasetRelationship).where(DatasetRelationship.business_id == business.id)
    ).all()

    names = {v.id: v.filename for v in all_versions}
    concepts = available_concepts(loaded.frames)
    return {
        "datasets": datasets,
        "entities": [
            {
                "type": e.entity_type,
                "name": e.display_name,
                "aliases": [a.raw_value for a in e.aliases],
            }
            for e in entities
        ],
        "relationships": [
            {
                "from": names.get(r.from_version_id, r.from_version_id),
                "from_column": r.from_column,
                "to": names.get(r.to_version_id, r.to_version_id),
                "to_column": r.to_column,
                "kind": r.kind,
                "confidence": r.confidence,
                "is_safe_join": r.is_safe_join,
                "reason": r.reason,
            }
            for r in relationships
        ],
        "concepts": {kind: sorted(items) for kind, items in concepts.items() if items},
        "readiness": readiness(concepts),
        "notes": loaded.notes,
    }


@router.get("/problems")
def problems(
    period_start: date | None = None,
    period_end: date | None = None,
    business: Business = Depends(get_owned_business),
    db: Session = Depends(get_db),
) -> dict:
    """Everything currently worth the owner's attention, in one list."""
    loaded = _scoped_frames(db, business, None, period_start, period_end)
    notes = loaded.notes
    comparison = compare_dimension(loaded.frames, "BRANCH")
    findings = [f.as_dict() for f in detect_branch_problems(comparison)]
    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))
    return {"findings": findings, "branches": comparison["members"], "notes": notes}

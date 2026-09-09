"""Upload, mapping confirmation and dataset inspection."""

from __future__ import annotations

from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.businesses import ensure_branch
from app.api.deps import get_current_user, get_owned_business
from app.db import get_db
from app.models import (
    Business,
    Confidence,
    Dataset,
    DatasetVersion,
    EntityKind,
    MappingMemory,
    QualityIssue,
    SemanticMapping,
    Severity,
    User,
)
from app.schemas import MappingOut, MappingUpdateBatch, UploadResult
from app.semantic.concepts import CONCEPTS
from app.semantic.engine import MappingProposal, detect_entity_kind, map_dataframe
from app.services.ingest import build_records
from app.services.layer import known_concepts, load_mapping_memory
from app.services.parsing import FileError, parse_upload
from app.services.profiling import profile_dataframe
from app.services.quality import assess_file
from app.services.layer import load_frames  # noqa: F401  (re-exported for routers/tests)

router = APIRouter(prefix="/api", tags=["datasets"])


def _owned_version(db: Session, user: User, version_id: int) -> DatasetVersion:
    version = db.scalar(
        select(DatasetVersion)
        .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
        .join(Business, Business.id == Dataset.business_id)
        .where(DatasetVersion.id == version_id, Business.owner_id == user.id)
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Dataset version not found")
    return version


@router.post(
    "/businesses/{business_id}/uploads",
    response_model=UploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset(
    file: UploadFile = File(...),
    dataset_name: str | None = Form(None),
    branch: str | None = Form(None),
    sheet: str | None = Form(None),
    period_start: date | None = Form(None),
    period_end: date | None = Form(None),
    business: Business = Depends(get_owned_business),
    db: Session = Depends(get_db),
) -> UploadResult:
    """Run the full pipeline: parse, profile, map, assess, clean, store."""
    content = await file.read()
    try:
        df, parse_report = parse_upload(file.filename or "upload", content, sheet=sheet)
    except FileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    profile, signals = profile_dataframe(df)
    # Record which sheet and header row were used so the user can correct us.
    profile["source"] = parse_report.as_dict()
    # First pass without memory to learn the kind, then with this business's
    # confirmed mappings applied.
    kind, _ = map_dataframe(df, signals)
    memory = load_mapping_memory(db, business.id, kind)
    kind, proposals = map_dataframe(df, signals, memory=memory)

    issues = assess_file(df, profile, proposals, kind)
    for note in parse_report.notes:
        issues.append(_scan_note(note))

    blocking = [i for i in issues if i.severity == "critical"]
    if blocking:
        raise HTTPException(status_code=422, detail={"errors": [i.as_dict() for i in blocking]})

    previously_seen = known_concepts(db, business.id, kind)
    new_concepts = sorted(
        {p.concept for p in proposals if p.concept} - previously_seen
    ) if previously_seen else []

    records, cleaning_log, derived_start, derived_end = build_records(df, proposals, branch)

    # Branches found in the file join the business's branch list, reconciled
    # against branches already registered under a different spelling.
    for name in {r["BRANCH"] for r in records if r.get("BRANCH")}:
        ensure_branch(db, business, str(name))

    resolved_start = period_start or derived_start
    resolved_end = period_end or derived_end
    if resolved_start is None or resolved_end is None:
        issues.append(
            _period_issue(file.filename or "This file")
        )

    dataset = _get_or_create_dataset(db, business, dataset_name or file.filename or "Dataset", kind)
    version = DatasetVersion(
        dataset_id=dataset.id,
        version=len(dataset.versions) + 1,
        filename=file.filename or "upload",
        entity_kind=EntityKind(kind),
        period_start=resolved_start,
        period_end=resolved_end,
        row_count=profile["row_count"],
        column_count=profile["column_count"],
        profile=profile,
        cleaning_log=cleaning_log,
        records=records,
    )
    db.add(version)
    db.flush()

    for proposal in proposals:
        db.add(_mapping_row(version.id, proposal))
    for issue in issues:
        db.add(
            QualityIssue(
                dataset_version_id=version.id,
                severity=Severity(issue.severity),
                code=issue.code,
                message=issue.message,
                column_name=issue.column_name,
                details=issue.details or {},
            )
        )
    db.commit()
    db.refresh(version)

    return _upload_result(version, new_concepts)


def _scan_note(message: str):
    """Something the workbook scanner decided, surfaced for the user to check."""
    from app.services.quality import Issue

    return Issue(severity="info", code="file_scan", message=message)


def _period_issue(filename: str):
    from app.services.quality import Issue

    return Issue(
        severity="warning",
        code="missing_period",
        message=(
            f"'{filename}' has no date column and no reporting period was given, so it "
            "cannot be included in month-by-month analysis. Re-upload it with a period."
        ),
    )


def _mapping_row(version_id: int, proposal: MappingProposal) -> SemanticMapping:
    return SemanticMapping(
        dataset_version_id=version_id,
        source_column=proposal.source_column,
        concept=proposal.concept,
        confidence=Confidence(proposal.confidence),
        score=proposal.score,
        rationale=proposal.rationale,
        needs_confirmation=proposal.needs_confirmation,
    )


def _get_or_create_dataset(
    db: Session, business: Business, name: str, kind: str
) -> Dataset:
    """Uploads with the same name and kind become versions of one dataset."""
    dataset = db.scalar(
        select(Dataset).where(
            Dataset.business_id == business.id,
            Dataset.name == name,
            Dataset.entity_kind == EntityKind(kind),
        )
    )
    if dataset is None:
        dataset = Dataset(business_id=business.id, name=name, entity_kind=EntityKind(kind))
        db.add(dataset)
        db.flush()
    return dataset


def _upload_result(version: DatasetVersion, new_concepts: list[str]) -> UploadResult:
    return UploadResult(
        dataset_id=version.dataset_id,
        dataset_version_id=version.id,
        filename=version.filename,
        entity_kind=version.entity_kind.value,
        row_count=version.row_count,
        column_count=version.column_count,
        period_start=version.period_start,
        period_end=version.period_end,
        profile=version.profile,
        mappings=[_mapping_out(m) for m in version.mappings],
        quality_issues=[
            {
                "severity": i.severity.value,
                "code": i.code,
                "message": i.message,
                "column_name": i.column_name,
                "details": i.details,
            }
            for i in version.quality_issues
        ],
        cleaning_log=version.cleaning_log,
        new_concepts=new_concepts,
        requires_confirmation=any(
            m.needs_confirmation and not m.confirmed_by_user for m in version.mappings
        ),
    )


def _mapping_out(m: SemanticMapping) -> MappingOut:
    return MappingOut(
        id=m.id,
        source_column=m.source_column,
        concept=m.concept,
        confidence=m.confidence.value,
        score=m.score,
        rationale=m.rationale,
        needs_confirmation=m.needs_confirmation,
        confirmed_by_user=m.confirmed_by_user,
    )


@router.get("/versions/{version_id}", response_model=UploadResult)
def get_version(
    version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> UploadResult:
    return _upload_result(_owned_version(db, user, version_id), [])


@router.patch("/versions/{version_id}/mappings", response_model=UploadResult)
def confirm_mappings(
    version_id: int,
    payload: MappingUpdateBatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UploadResult:
    """Apply the user's answers and rebuild the canonical records.

    The rebuild reads back the preserved ``_raw`` payload, so a correction
    re-runs cleaning against the original file contents rather than against
    already-transformed values.
    """
    version = _owned_version(db, user, version_id)
    by_id = {m.id: m for m in version.mappings}

    for update in payload.updates:
        mapping = by_id.get(update.mapping_id)
        if mapping is None:
            raise HTTPException(
                status_code=404, detail=f"Mapping {update.mapping_id} is not on this version."
            )
        if update.concept is not None and update.concept not in CONCEPTS:
            raise HTTPException(status_code=422, detail=f"Unknown concept '{update.concept}'.")

        mapping.concept = update.concept
        mapping.confidence = Confidence.HIGH
        mapping.score = 1.0
        mapping.rationale = "confirmed by user"
        mapping.needs_confirmation = False
        mapping.confirmed_by_user = True

        if update.remember:
            _remember(db, version, mapping.source_column, update.concept)

    _rebuild_records(db, version)
    _recompute_entity_kind(db, version)
    db.commit()
    db.refresh(version)
    return _upload_result(version, [])


def _remember(
    db: Session, version: DatasetVersion, source_column: str, concept: str | None
) -> None:
    business_id = version.dataset.business_id
    existing = db.scalar(
        select(MappingMemory).where(
            MappingMemory.business_id == business_id,
            MappingMemory.source_column == source_column,
            MappingMemory.entity_kind == version.entity_kind,
        )
    )
    if existing:
        existing.concept = concept
        return
    db.add(
        MappingMemory(
            business_id=business_id,
            source_column=source_column,
            entity_kind=version.entity_kind,
            concept=concept,
        )
    )


def _recompute_entity_kind(db: Session, version: DatasetVersion) -> None:
    """Re-classify a version once the user has confirmed what its columns mean.

    A file we could not classify on upload is stored but inert -- the semantic
    layer skips unknown data. Confirming the mappings is what makes it live, so
    the kind has to be derived again here rather than only at upload.
    """
    proposals = [
        MappingProposal(m.source_column, m.concept, m.score, m.confidence.value, "", [])
        for m in version.mappings
    ]
    kind = detect_entity_kind(proposals)
    if kind == "unknown" or kind == version.entity_kind.value:
        return

    version.entity_kind = EntityKind(kind)
    dataset = version.dataset
    if dataset.entity_kind is EntityKind.UNKNOWN:
        dataset.entity_kind = EntityKind(kind)


def _rebuild_records(db: Session, version: DatasetVersion) -> None:
    raw_rows = [r.get("_raw", {}) for r in (version.records or [])]
    if not raw_rows:
        return
    df = pd.DataFrame(raw_rows)
    proposals = [
        MappingProposal(
            source_column=m.source_column,
            concept=m.concept,
            score=m.score,
            confidence=m.confidence.value,
            rationale=m.rationale,
            alternatives=[],
        )
        for m in version.mappings
    ]
    records, cleaning_log, start, end = build_records(df, proposals)
    version.records = records
    version.cleaning_log = cleaning_log
    if start and end:
        version.period_start, version.period_end = start, end


@router.get("/businesses/{business_id}/datasets")
def list_datasets(
    business: Business = Depends(get_owned_business), db: Session = Depends(get_db)
) -> list[dict]:
    datasets = db.scalars(select(Dataset).where(Dataset.business_id == business.id)).all()
    return [
        {
            "id": d.id,
            "name": d.name,
            "entity_kind": d.entity_kind.value,
            "versions": [
                {
                    "id": v.id,
                    "version": v.version,
                    "filename": v.filename,
                    "row_count": v.row_count,
                    "period_start": v.period_start,
                    "period_end": v.period_end,
                    "is_active": v.is_active,
                    "requires_confirmation": any(
                        m.needs_confirmation and not m.confirmed_by_user for m in v.mappings
                    ),
                }
                for v in d.versions
            ],
        }
        for d in datasets
    ]

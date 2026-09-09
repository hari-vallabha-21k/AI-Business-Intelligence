"""Business workspace and branch setup (process doc sec. 1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_business
from app.db import get_db
from app.models import Branch, Business, User
from app.schemas import BranchCreate, BranchOut, BusinessCreate, BusinessOut
from app.services.cleaning import normalize_label

router = APIRouter(prefix="/api/businesses", tags=["businesses"])


def ensure_branch(db: Session, business: Business, name: str) -> Branch:
    """Get or create a branch, reconciling spelling variants of an existing one."""
    normalized = normalize_label(name)
    if not normalized:
        raise HTTPException(status_code=422, detail="Branch name cannot be empty.")
    existing = db.scalar(
        select(Branch).where(
            Branch.business_id == business.id, Branch.normalized_name == normalized
        )
    )
    if existing:
        return existing
    branch = Branch(business_id=business.id, name=name.strip(), normalized_name=normalized)
    db.add(branch)
    db.flush()
    return branch


@router.post("", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
def create_business(
    payload: BusinessCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Business:
    business = Business(
        owner_id=user.id,
        name=payload.name,
        business_type=payload.business_type,
        currency=payload.currency,
    )
    db.add(business)
    db.flush()
    for branch_name in payload.branches:
        ensure_branch(db, business, branch_name)
    db.commit()
    db.refresh(business)
    return business


@router.get("", response_model=list[BusinessOut])
def list_businesses(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Business]:
    return list(db.scalars(select(Business).where(Business.owner_id == user.id)))


@router.get("/{business_id}", response_model=BusinessOut)
def get_business(business: Business = Depends(get_owned_business)) -> Business:
    return business


@router.post("/{business_id}/branches", response_model=BranchOut, status_code=201)
def add_branch(
    payload: BranchCreate,
    business: Business = Depends(get_owned_business),
    db: Session = Depends(get_db),
) -> Branch:
    branch = ensure_branch(db, business, payload.name)
    db.commit()
    db.refresh(branch)
    return branch


@router.get("/{business_id}/branches", response_model=list[BranchOut])
def list_branches(
    business: Business = Depends(get_owned_business), db: Session = Depends(get_db)
) -> list[Branch]:
    return list(db.scalars(select(Branch).where(Branch.business_id == business.id)))

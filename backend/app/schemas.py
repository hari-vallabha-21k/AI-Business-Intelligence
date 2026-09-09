"""Request and response models."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str | None = None


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str | None = None

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    business_type: str = "restaurant"
    currency: str = Field(default="INR", max_length=8)
    branches: list[str] = Field(default_factory=list)


class BranchOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class BusinessOut(BaseModel):
    id: int
    name: str
    business_type: str
    currency: str
    branches: list[BranchOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class BranchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class MappingOut(BaseModel):
    id: int
    source_column: str
    concept: str | None
    confidence: str
    score: float
    rationale: str
    needs_confirmation: bool
    confirmed_by_user: bool

    model_config = {"from_attributes": True}


class MappingUpdate(BaseModel):
    """A user's answer to "what does this column represent?" (PRD sec. 14).

    ``concept=None`` means ignore the column.
    """

    mapping_id: int
    concept: str | None = None
    remember: bool = True


class MappingUpdateBatch(BaseModel):
    updates: list[MappingUpdate]


class QualityIssueOut(BaseModel):
    severity: str
    code: str
    message: str
    column_name: str | None = None
    details: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class UploadResult(BaseModel):
    dataset_id: int
    dataset_version_id: int
    filename: str
    entity_kind: str
    row_count: int
    column_count: int
    period_start: date | None = None
    period_end: date | None = None
    profile: dict
    mappings: list[MappingOut]
    quality_issues: list[QualityIssueOut]
    cleaning_log: list[dict]
    new_concepts: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class AnalysisScope(BaseModel):
    branches: list[str] | None = None
    period_start: date | None = None
    period_end: date | None = None

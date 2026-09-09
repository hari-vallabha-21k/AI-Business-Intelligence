"""Relational model for the business semantic layer.

The schema is multi-tenant: every row below a ``Business`` is reachable only
through that business, and every query path in the API filters on the caller's
membership (see ``app.api.deps``).

Uploaded rows are not stored in a per-file physical table. Each dataset version
keeps its rows as canonical records -- dictionaries keyed by canonical concept
(``REVENUE``, ``BRANCH``, ``EMPLOYEE_COMPENSATION``...) -- so that a January file
with ``food_sales`` and a February file with ``food_revenue`` land in the same
analytical shape (PRD sec. 19-20).
"""

from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EntityKind(str, enum.Enum):
    """What a dataset is fundamentally about (process doc sec. 5)."""

    SALES = "sales"
    EMPLOYEE = "employee"
    EXPENSE = "expense"
    UNKNOWN = "unknown"


class Confidence(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Severity(str, enum.Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    businesses: Mapped[list["Business"]] = relationship(back_populates="owner")


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    business_type: Mapped[str] = mapped_column(String(64), default="restaurant")
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    owner: Mapped[User] = relationship(back_populates="businesses")
    branches: Mapped[list["Branch"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    datasets: Mapped[list["Dataset"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )


class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("business_id", "normalized_name", name="uq_branch_norm"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    # Lower-cased, punctuation-stripped form used to reconcile "Jubilee Hills",
    # "jubilee hills" and "Jubilee-Hills" (PRD sec. 11).
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    business: Mapped[Business] = relationship(back_populates="branches")


class Dataset(Base):
    """A logical stream of uploads, e.g. "Monthly sales"."""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    entity_kind: Mapped[EntityKind] = mapped_column(Enum(EntityKind), default=EntityKind.UNKNOWN)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    business: Mapped[Business] = relationship(back_populates="datasets")
    versions: Mapped[list["DatasetVersion"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", order_by="DatasetVersion.version"
    )


class DatasetVersion(Base):
    """One uploaded file: its profile, its mappings and its canonical rows."""

    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    filename: Mapped[str] = mapped_column(String(512))
    entity_kind: Mapped[EntityKind] = mapped_column(Enum(EntityKind), default=EntityKind.UNKNOWN)

    # Reporting period. period_start/end are derived from date columns when present,
    # otherwise supplied by the user at upload time.
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)

    row_count: Mapped[int] = mapped_column(Integer, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    cleaning_log: Mapped[list] = mapped_column(JSON, default=list)
    # Rows keyed by canonical concept; the raw row is kept alongside so the
    # original data is never destroyed (PRD sec. 11).
    records: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    dataset: Mapped[Dataset] = relationship(back_populates="versions")
    mappings: Mapped[list["SemanticMapping"]] = relationship(
        back_populates="dataset_version", cascade="all, delete-orphan"
    )
    quality_issues: Mapped[list["QualityIssue"]] = relationship(
        back_populates="dataset_version", cascade="all, delete-orphan"
    )


class SemanticMapping(Base):
    """Source column -> canonical concept, with the confidence behind it."""

    __tablename__ = "semantic_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_version_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True
    )
    source_column: Mapped[str] = mapped_column(String(255))
    concept: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[Confidence] = mapped_column(Enum(Confidence), default=Confidence.LOW)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[str] = mapped_column(Text, default="")
    needs_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, default=False)

    dataset_version: Mapped[DatasetVersion] = relationship(back_populates="mappings")


class MappingMemory(Base):
    """A user's confirmed mapping, reused for later uploads (PRD sec. 14)."""

    __tablename__ = "mapping_memory"
    __table_args__ = (
        UniqueConstraint("business_id", "source_column", "entity_kind", name="uq_memory_column"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    source_column: Mapped[str] = mapped_column(String(255))
    entity_kind: Mapped[EntityKind] = mapped_column(Enum(EntityKind), default=EntityKind.UNKNOWN)
    concept: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class QualityIssue(Base):
    __tablename__ = "quality_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_version_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True
    )
    severity: Mapped[Severity] = mapped_column(Enum(Severity), default=Severity.INFO)
    code: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    column_name: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    dataset_version: Mapped[DatasetVersion] = relationship(back_populates="quality_issues")

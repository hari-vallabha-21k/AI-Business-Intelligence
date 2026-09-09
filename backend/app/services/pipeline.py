"""The data-understanding pipeline (PRD sec. 4, phase 1).

One place that runs the stages in order and returns everything learned about an
upload, so the API route stays a thin wrapper and the whole pipeline can be
tested without HTTP:

    ingest -> profile -> map -> normalise -> grain -> classify -> resolve
    -> quality

Relationship discovery needs the other datasets, so it runs separately once the
version is stored.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import pandas as pd

from app.semantic.classification import Classification, classify
from app.semantic.engine import MappingProposal, map_dataframe
from app.semantic.grain import Grain, detect_grain
from app.semantic.resolution import Resolution, resolve_values
from app.services.ingest import build_records, records_to_frame
from app.services.profiling import profile_dataframe
from app.services.quality import Issue, assess_file
from app.services.workbook import ParseReport

# Entity types resolved at upload time. Employees are deliberately excluded:
# people share names, and merging two employees is worse than leaving them apart.
RESOLVED_ENTITY_TYPES = ("BRANCH", "DEPARTMENT")


@dataclass
class PipelineResult:
    frame: pd.DataFrame
    profile: dict
    proposals: list[MappingProposal]
    records: list[dict]
    cleaning_log: list[dict]
    grain: Grain
    classification: Classification
    resolutions: dict[str, list[Resolution]] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    period_start = None
    period_end = None
    content_hash: str = ""
    schema_hash: str = ""


def content_hash(content: bytes) -> str:
    """Identity of the uploaded bytes, for detecting a re-upload."""
    return hashlib.sha256(content).hexdigest()


def schema_hash(columns) -> str:
    """Identity of the column set, for detecting a schema change."""
    joined = "|".join(sorted(str(c).strip().lower() for c in columns))
    return hashlib.sha256(joined.encode()).hexdigest()


def run(
    frame: pd.DataFrame,
    content: bytes,
    filename: str,
    parse_report: ParseReport | None = None,
    memory: dict[str, str | None] | None = None,
    default_branch: str | None = None,
    known_entities: dict[str, dict[str, str]] | None = None,
) -> PipelineResult:
    """Run every understanding stage over one parsed file."""
    profile, signals = profile_dataframe(frame)
    if parse_report:
        profile["source"] = parse_report.as_dict()

    _, proposals = map_dataframe(frame, signals, memory=memory)
    records, cleaning_log, period_start, period_end = build_records(
        frame, proposals, default_branch
    )
    canonical = records_to_frame(records)

    # Grain before classification: it is what separates an invoice from its
    # line items, which no column name reveals.
    grain = detect_grain(canonical)
    classification = classify(
        proposals,
        filename=filename,
        sheet_name=parse_report.sheet_name if parse_report else None,
        grain_keys=grain.keys,
    )

    # Resolution runs on the values as they appear in the file, not on the
    # cleaned ones: the point of the alias table is to record what the user
    # actually wrote, so the link back to their spreadsheet stays visible.
    resolutions: dict[str, list[Resolution]] = {}
    for entity_type in RESOLVED_ENTITY_TYPES:
        if entity_type not in canonical.columns:
            continue
        source_column = next(
            (p.source_column for p in proposals if p.concept == entity_type), None
        )
        if source_column and source_column in frame.columns:
            values = [str(v) for v in frame[source_column].dropna().unique()]
        else:
            values = [str(v) for v in canonical[entity_type].dropna().unique()]
        if values:
            resolutions[entity_type] = resolve_values(
                values, (known_entities or {}).get(entity_type, {})
            )

    issues = assess_file(frame, profile, proposals, classification.entity_kind)
    issues.extend(_pipeline_issues(grain, classification, resolutions))

    result = PipelineResult(
        frame=frame,
        profile=profile,
        proposals=proposals,
        records=records,
        cleaning_log=cleaning_log,
        grain=grain,
        classification=classification,
        resolutions=resolutions,
        issues=issues,
        content_hash=content_hash(content),
        schema_hash=schema_hash(frame.columns),
    )
    result.period_start = period_start
    result.period_end = period_end
    return result


def _pipeline_issues(
    grain: Grain, classification: Classification, resolutions: dict[str, list[Resolution]]
) -> list[Issue]:
    issues: list[Issue] = []

    if grain.is_ambiguous:
        issues.append(
            Issue(
                "warning",
                "ambiguous_grain",
                "We couldn't determine what a single row represents, so totals from this "
                "file may double count. Check for repeated rows or a missing identifier.",
                details=grain.as_dict(),
            )
        )
    else:
        issues.append(
            Issue("info", "grain_detected", f"We read this file as: {grain.description}.",
                  details=grain.as_dict())
        )
        if grain.duplicate_rows:
            issues.append(
                Issue(
                    "warning",
                    "duplicate_keys",
                    f"{grain.duplicate_rows:,} rows repeat a value that should be unique "
                    f"({', '.join(grain.keys)}). They may be duplicates.",
                    details={"count": grain.duplicate_rows},
                )
            )

    if classification.needs_review:
        issues.append(
            Issue(
                "warning",
                "low_confidence_classification",
                f"We think this is {classification.category.replace('_', ' ')} data, but "
                f"only with {classification.confidence:.0%} confidence. Please confirm.",
                details=classification.as_dict(),
            )
        )
    else:
        issues.append(
            Issue(
                "info",
                "classified",
                f"Identified as {classification.category.replace('_', ' ')} data "
                f"({classification.confidence:.0%} confidence).",
                details=classification.as_dict(),
            )
        )

    for entity_type, items in resolutions.items():
        ambiguous = [r for r in items if r.needs_user]
        for resolution in ambiguous:
            options = ", ".join(c.display_name for c in resolution.candidates[:3])
            issues.append(
                Issue(
                    "warning",
                    "ambiguous_entity",
                    f"'{resolution.raw_value}' could be {options}. Please confirm which "
                    f"{entity_type.lower()} it is.",
                    column_name=entity_type,
                    details=resolution.as_dict(),
                )
            )
    return issues

"""The semantic engine is where a wrong answer does the most damage."""

from __future__ import annotations

import pandas as pd
import pytest

from app.semantic.engine import (
    ColumnSignals,
    detect_entity_kind,
    map_dataframe,
    normalize,
    score_column,
)
from app.services.profiling import profile_dataframe


def signals(name, **kwargs):
    base = dict(dtype="object", non_null=100, unique=50, total=100)
    base.update(kwargs)
    return ColumnSignals(name=name, **base)


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ("salary", "EMPLOYEE_COMPENSATION"),
        ("monthly_salary", "EMPLOYEE_COMPENSATION"),
        ("monthly_pay", "EMPLOYEE_COMPENSATION"),
        ("Gross Pay (INR)", "EMPLOYEE_COMPENSATION"),
    ],
)
def test_compensation_synonyms_map_to_one_concept(column, expected):
    """PRD sec. 13: different names, same canonical concept."""
    proposal = score_column(
        signals(column, numeric_share=1.0, unique=90, mean=45000), "employee"
    )
    assert proposal.concept == expected
    assert proposal.confidence == "high"


@pytest.mark.parametrize("column", ["branch", "location", "store", "outlet", "branch_name"])
def test_branch_synonyms(column):
    assert score_column(signals(column, unique=3), "sales").concept == "BRANCH"


def test_measure_rejected_when_values_are_not_numeric():
    """A column named 'salary' full of text is not compensation."""
    proposal = score_column(signals("salary", numeric_share=0.0, unique=4), "employee")
    assert proposal.concept != "EMPLOYEE_COMPENSATION"


def test_date_concept_requires_parseable_dates():
    assert score_column(signals("date", numeric_share=1.0, date_share=0.0)).concept != "DATE"
    assert score_column(signals("order_date", date_share=1.0)).concept == "DATE"


def test_unknown_column_is_low_confidence_not_a_guess():
    """PRD sec. 14: 'extra' must be asked about, never assumed."""
    proposal = score_column(signals("extra", numeric_share=1.0, mean=120), "sales")
    assert proposal.confidence == "low"
    assert proposal.needs_confirmation


def test_january_and_february_schemas_converge(monkeypatch):
    """PRD sec. 20: renamed columns land on the same concepts."""
    january = pd.DataFrame(
        {"food_sales": [100.0, 200.0], "service_charge": [5.0, 6.0],
         "gst": [9.0, 18.0], "bill_no": ["a", "b"]}
    )
    february = pd.DataFrame(
        {"food_revenue": [110.0, 210.0], "service_fee": [5.5, 6.5],
         "tax": [10.0, 19.0], "invoice_no": ["c", "d"]}
    )
    jan_kind, jan_props = map_dataframe(january, profile_dataframe(january)[1])
    feb_kind, feb_props = map_dataframe(february, profile_dataframe(february)[1])

    jan_concepts = {p.concept for p in jan_props if p.concept}
    feb_concepts = {p.concept for p in feb_props if p.concept}
    assert jan_kind == feb_kind == "sales"
    assert {"REVENUE", "SERVICE_CHARGE", "TAX", "ORDER_ID"} <= jan_concepts
    assert jan_concepts == feb_concepts


def test_entity_kinds_are_distinguished(sales_df, employee_df):
    for df, expected in ((sales_df, "sales"), (employee_df, "employee")):
        kind, _ = map_dataframe(df, profile_dataframe(df)[1])
        assert kind == expected


def test_one_dimension_is_not_claimed_by_two_columns():
    df = pd.DataFrame(
        {"branch": ["A", "B"], "outlet": ["A", "B"], "revenue": [10.0, 20.0],
         "order_id": ["o1", "o2"]}
    )
    _, proposals = map_dataframe(df, profile_dataframe(df)[1])
    branch_claims = [p for p in proposals if p.concept == "BRANCH"]
    assert len(branch_claims) == 1
    loser = next(p for p in proposals if p.source_column in {"branch", "outlet"} and not p.concept)
    assert "stronger match" in loser.rationale


def test_confirmed_mapping_is_reused():
    """PRD sec. 14: a user's correction is remembered."""
    memory = {normalize("extra"): "SERVICE_CHARGE"}
    proposal = score_column(signals("extra", numeric_share=1.0), "sales", memory=memory)
    assert proposal.concept == "SERVICE_CHARGE"
    assert proposal.confidence == "high"
    assert not proposal.needs_confirmation


def test_entity_detection_needs_two_signals():
    from app.semantic.engine import MappingProposal

    one = [MappingProposal("revenue", "REVENUE", 0.9, "high", "", [])]
    assert detect_entity_kind(one) == "unknown"

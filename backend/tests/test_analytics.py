"""Analytics must never invent a number the data cannot support."""

from __future__ import annotations

import pandas as pd
import pytest

from app.analytics.comparison import compare_dimension, compare_metrics
from app.analytics.engine import evaluate, split_by
from app.analytics.problems import (
    contribution_analysis,
    detect_branch_problems,
    detect_period_problems,
)


def frames(revenue=None, pay=None, expense=None):
    out = {}
    if revenue:
        out["sales"] = pd.DataFrame(revenue)
    if pay:
        out["employee"] = pd.DataFrame(pay)
    if expense:
        out["expense"] = pd.DataFrame(expense)
    return out


def test_metric_is_unavailable_rather_than_wrong():
    """Process doc sec. 7: profit is withheld, not assumed to be revenue."""
    results = evaluate(frames(revenue={"REVENUE": [100.0, 200.0], "BRANCH": ["A", "B"]}))
    assert results["total_revenue"].value == 300.0
    profit = results["operating_profit"]
    assert not profit.available
    assert profit.value is None
    assert "Cost of goods sold" in profit.reason


def test_unavailable_reason_names_the_missing_concept():
    results = evaluate(frames(revenue={"REVENUE": [100.0]}))
    assert "Employee compensation in employee data" in results["total_employee_cost"].reason


def test_full_profit_chain_when_every_component_is_present():
    results = evaluate(
        frames(
            revenue={"REVENUE": [1000.0], "COGS": [350.0], "BRANCH": ["A"]},
            pay={"EMPLOYEE_COMPENSATION": [200.0], "EMPLOYEE_ID": ["e1"], "BRANCH": ["A"]},
            expense={"OPERATING_EXPENSE": [150.0], "BRANCH": ["A"]},
        )
    )
    assert results["gross_profit"].value == 650.0
    assert results["operating_profit"].value == 300.0
    assert results["operating_margin"].value == pytest.approx(30.0)
    assert results["employee_cost_ratio"].value == pytest.approx(20.0)


def test_employee_cost_includes_overtime_and_incentives():
    results = evaluate(
        frames(pay={
            "EMPLOYEE_ID": ["e1", "e2"],
            "EMPLOYEE_COMPENSATION": [100.0, 100.0],
            "OVERTIME_PAY": [10.0, 5.0],
            "INCENTIVE": [20.0, 0.0],
        })
    )
    assert results["total_employee_cost"].value == 235.0
    assert results["average_salary"].value == pytest.approx(117.5)


def test_all_null_column_supports_nothing():
    """A column that exists but is entirely empty is not data."""
    results = evaluate(frames(revenue={"REVENUE": [None, None], "BRANCH": ["A", "B"]}))
    assert not results["total_revenue"].available


def test_division_by_zero_yields_unavailable_not_infinity():
    results = evaluate(
        frames(
            revenue={"REVENUE": [0.0], "BRANCH": ["A"]},
            pay={"EMPLOYEE_COMPENSATION": [100.0], "EMPLOYEE_ID": ["e1"], "BRANCH": ["A"]},
        )
    )
    assert not results["employee_cost_ratio"].available


def test_available_metric_carries_its_formula_as_evidence():
    """PRD sec. 25: every answer must be inspectable."""
    results = evaluate(
        frames(
            revenue={"REVENUE": [1000.0], "BRANCH": ["A"]},
            pay={"EMPLOYEE_COMPENSATION": [200.0], "EMPLOYEE_ID": ["e1"], "BRANCH": ["A"]},
        )
    )
    ratio = results["employee_cost_ratio"].as_dict()
    assert ratio["formula"] == "Employee cost / Total revenue x 100"
    assert ratio["inputs"] == {"total_employee_cost": 200.0, "total_revenue": 1000.0}


def test_split_by_branch_does_not_duplicate_company_level_costs():
    """An expense sheet with no branch column must not be charged to every branch."""
    f = frames(
        revenue={"REVENUE": [100.0, 200.0], "BRANCH": ["A", "B"]},
        expense={"OPERATING_EXPENSE": [500.0]},  # no BRANCH column
    )
    slices = split_by(f, "BRANCH")
    assert set(slices) == {"A", "B"}
    assert all("expense" not in s for s in slices.values())


def test_branch_ranking_only_uses_metrics_every_branch_has():
    f = frames(
        revenue={"REVENUE": [100.0, 200.0], "BRANCH": ["A", "B"]},
        pay={"EMPLOYEE_COMPENSATION": [50.0], "EMPLOYEE_ID": ["e1"], "BRANCH": ["A"]},
    )
    comparison = compare_dimension(f, "BRANCH")
    revenue_row = next(r for r in comparison["metrics"] if r["key"] == "total_revenue")
    cost_row = next(r for r in comparison["metrics"] if r["key"] == "total_employee_cost")
    assert revenue_row["comparable"] and revenue_row["best"] == "B"
    assert not cost_row["comparable"]
    assert "Not comparable" in cost_row["note"]


def test_lower_is_better_metrics_rank_the_right_way_up():
    f = frames(
        revenue={"REVENUE": [1000.0, 1000.0], "BRANCH": ["A", "B"]},
        pay={
            "EMPLOYEE_COMPENSATION": [400.0, 200.0],
            "EMPLOYEE_ID": ["e1", "e2"],
            "BRANCH": ["A", "B"],
        },
    )
    comparison = compare_dimension(f, "BRANCH")
    ratio = next(r for r in comparison["metrics"] if r["key"] == "employee_cost_ratio")
    assert ratio["best"] == "B" and ratio["worst"] == "A"


def test_cost_growing_faster_than_revenue_is_detected():
    """PRD sec. 21."""
    current = evaluate(
        frames(
            revenue={"REVENUE": [108.0], "BRANCH": ["A"]},
            pay={"EMPLOYEE_COMPENSATION": [121.0], "EMPLOYEE_ID": ["e1"], "BRANCH": ["A"]},
        )
    )
    previous = evaluate(
        frames(
            revenue={"REVENUE": [100.0], "BRANCH": ["A"]},
            pay={"EMPLOYEE_COMPENSATION": [100.0], "EMPLOYEE_ID": ["e1"], "BRANCH": ["A"]},
        )
    )
    findings = detect_period_problems(compare_metrics(current, previous))
    codes = {f.code for f in findings}
    assert "total_employee_cost_outgrowing_revenue" in codes
    finding = next(f for f in findings if f.code == "total_employee_cost_outgrowing_revenue")
    assert finding.kind == "fact"


def test_causal_claims_are_labelled_as_hypotheses():
    """PRD sec. 23: a possible explanation is never stated as fact."""
    def build(rev, pay, heads):
        return evaluate(
            frames(
                revenue={"REVENUE": [rev], "BRANCH": ["A"]},
                pay={
                    "EMPLOYEE_COMPENSATION": [pay / heads] * heads,
                    "EMPLOYEE_ID": [f"e{i}" for i in range(heads)],
                    "BRANCH": ["A"] * heads,
                },
            )
        )

    findings = detect_period_problems(
        compare_metrics(build(108.0, 121.0, 7), build(100.0, 100.0, 6))
    )
    hypotheses = [f for f in findings if f.kind == "hypothesis"]
    assert hypotheses, "expected a hypothesis about pay rates"
    assert "does not distinguish" in hypotheses[0].detail
    assert all(f.kind != "fact" or "may" not in f.detail for f in findings)


def test_contribution_analysis_reports_share_not_cause():
    """PRD sec. 22: decomposition, not a claim about why."""
    def by_branch(a, b):
        return {
            "Branch A": evaluate(frames(revenue={"REVENUE": [a], "BRANCH": ["Branch A"]})),
            "Branch B": evaluate(frames(revenue={"REVENUE": [b], "BRANCH": ["Branch B"]})),
        }

    findings = contribution_analysis(by_branch(190.0, 105.0), by_branch(100.0, 100.0),
                                     "total_revenue")
    assert findings[0].kind == "driver"
    assert "Branch A" in findings[0].title
    assert findings[0].evidence["contributions"] == {"Branch A": 90.0, "Branch B": 5.0}


def test_branch_moving_against_the_trend_is_surfaced():
    def by_branch(a, b):
        return {
            "Branch A": evaluate(frames(revenue={"REVENUE": [a], "BRANCH": ["Branch A"]})),
            "Branch B": evaluate(frames(revenue={"REVENUE": [b], "BRANCH": ["Branch B"]})),
        }

    findings = contribution_analysis(by_branch(200.0, 80.0), by_branch(100.0, 100.0),
                                     "total_revenue")
    codes = {f.code for f in findings}
    assert "total_revenue_divergent_members" in codes


def test_loss_making_branch_is_flagged():
    f = frames(
        revenue={"REVENUE": [100.0, 1000.0], "COGS": [50.0, 300.0], "BRANCH": ["A", "B"]},
        pay={
            "EMPLOYEE_COMPENSATION": [400.0, 200.0],
            "EMPLOYEE_ID": ["e1", "e2"],
            "BRANCH": ["A", "B"],
        },
        expense={"OPERATING_EXPENSE": [50.0, 100.0], "BRANCH": ["A", "B"]},
    )
    findings = detect_branch_problems(compare_dimension(f, "BRANCH"))
    assert any(f.code == "loss_making_branch" for f in findings)

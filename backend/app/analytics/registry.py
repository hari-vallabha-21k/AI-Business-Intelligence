"""Metric registry.

Every metric declares exactly what it needs. Nothing is computed from data that
cannot support it -- a profit figure is never produced by assuming a missing
cost is zero (PRD sec. 6B, process doc sec. 7). Each result also carries the
formula and its inputs so the UI can show "view calculation" (PRD sec. 25).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import pandas as pd

from app.semantic.concepts import label as concept_label

Frames = dict[str, pd.DataFrame]
Context = dict[str, float]


def _sum(frames: Frames, entity: str, concept: str) -> float:
    df = frames.get(entity)
    if df is None or concept not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[concept], errors="coerce").sum())


def _sum_any(frames: Frames, entity: str, concepts: Sequence[str]) -> float:
    return sum(_sum(frames, entity, c) for c in concepts)


def _nunique(frames: Frames, entity: str, concept: str) -> float:
    df = frames.get(entity)
    if df is None or concept not in df.columns:
        return 0.0
    return float(df[concept].dropna().nunique())


def _rows(frames: Frames, entity: str) -> float:
    df = frames.get(entity)
    return float(len(df)) if df is not None else 0.0


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str  # currency | count | ratio | percent
    formula: str
    fn: Callable[[Frames, Context], float | None]
    # All of these concepts must be present, as (entity_kind, concept) pairs.
    requires: tuple[tuple[str, str], ...] = ()
    # At least one pair from each group must be present.
    requires_any: tuple[tuple[tuple[str, str], ...], ...] = ()
    depends_on: tuple[str, ...] = ()
    higher_is_better: bool | None = True
    # Whether the members of a dimension sum to the whole. Only additive metrics
    # can be decomposed by branch: the branch shares of a margin or an average
    # do not add up to the company figure, so "who drove the change" is not a
    # question those metrics can answer.
    decomposable: bool = False
    # Whether ranking members against each other is meaningful. An absolute cost
    # total is not: the smallest branch always spends the least, which says
    # nothing about how well it is run. Ratios and per-unit figures are.
    rankable: bool = True
    description: str = ""
    inputs: tuple[str, ...] = field(default=())

    def missing_requirements(self, available: dict[str, set[str]]) -> list[str]:
        missing = [
            f"{entity}.{concept}"
            for entity, concept in self.requires
            if concept not in available.get(entity, set())
        ]
        for group in self.requires_any:
            if not any(concept in available.get(entity, set()) for entity, concept in group):
                missing.append(" or ".join(f"{e}.{c}" for e, c in group))
        return missing

    def explain_missing(self, missing: Sequence[str]) -> str:
        if not missing:
            return ""
        parts = []
        for item in missing:
            readable = " or ".join(
                f"{concept_label(token.split('.', 1)[1])} in {token.split('.', 1)[0]} data"
                for token in item.split(" or ")
            )
            parts.append(readable)
        return f"{self.label} needs {'; '.join(parts)}."

    def is_available(self, available: dict[str, set[str]], computed: Context) -> bool:
        if self.missing_requirements(available):
            return False
        return all(dep in computed for dep in self.depends_on)


def _ratio(numerator: float, denominator: float) -> float | None:
    return None if not denominator else numerator / denominator


# Compensation is base pay plus whatever variable pay the file happens to carry.
_PAY_CONCEPTS = ("EMPLOYEE_COMPENSATION", "OVERTIME_PAY", "INCENTIVE")

METRICS: tuple[Metric, ...] = (
    Metric(
        key="total_revenue",
        label="Total revenue",
        unit="currency",
        formula="SUM(REVENUE)",
        requires=(("sales", "REVENUE"),),
        fn=lambda f, _: _sum(f, "sales", "REVENUE"),
        description="Money billed across all sales rows in scope.",
        decomposable=True,
    ),
    Metric(
        key="total_discount",
        label="Total discount",
        unit="currency",
        formula="SUM(DISCOUNT)",
        requires=(("sales", "DISCOUNT"),),
        higher_is_better=False,
        fn=lambda f, _: _sum(f, "sales", "DISCOUNT"),
        decomposable=True,
        rankable=False,
    ),
    Metric(
        key="total_tax",
        label="Total tax",
        unit="currency",
        formula="SUM(TAX)",
        requires=(("sales", "TAX"),),
        higher_is_better=None,
        fn=lambda f, _: _sum(f, "sales", "TAX"),
        decomposable=True,
        rankable=False,
    ),
    Metric(
        key="net_revenue",
        label="Net revenue",
        unit="currency",
        formula="Total revenue - Total discount",
        requires=(("sales", "REVENUE"), ("sales", "DISCOUNT")),
        depends_on=("total_revenue", "total_discount"),
        fn=lambda _, c: c["total_revenue"] - c["total_discount"],
        description="Revenue after discounts, before tax and cost.",
        decomposable=True,
    ),
    Metric(
        key="total_orders",
        label="Total orders",
        unit="count",
        formula="COUNT(DISTINCT ORDER_ID)",
        requires=(("sales", "ORDER_ID"),),
        fn=lambda f, _: _nunique(f, "sales", "ORDER_ID"),
        decomposable=True,
    ),
    Metric(
        key="total_quantity",
        label="Units sold",
        unit="count",
        formula="SUM(QUANTITY)",
        requires=(("sales", "QUANTITY"),),
        fn=lambda f, _: _sum(f, "sales", "QUANTITY"),
        decomposable=True,
    ),
    Metric(
        key="average_order_value",
        label="Average order value",
        unit="currency",
        formula="Total revenue / Total orders",
        requires=(("sales", "REVENUE"), ("sales", "ORDER_ID")),
        depends_on=("total_revenue", "total_orders"),
        fn=lambda _, c: _ratio(c["total_revenue"], c["total_orders"]),
    ),
    Metric(
        key="unique_customers",
        label="Unique customers",
        unit="count",
        formula="COUNT(DISTINCT CUSTOMER_ID)",
        requires=(("sales", "CUSTOMER_ID"),),
        fn=lambda f, _: _nunique(f, "sales", "CUSTOMER_ID"),
        decomposable=True,
    ),
    # --- Workforce --------------------------------------------------------------
    Metric(
        key="employee_count",
        label="Employees",
        unit="count",
        formula="COUNT(DISTINCT EMPLOYEE_ID)",
        requires_any=((("employee", "EMPLOYEE_ID"), ("employee", "EMPLOYEE_NAME")),),
        fn=lambda f, _: (
            _nunique(f, "employee", "EMPLOYEE_ID")
            or _nunique(f, "employee", "EMPLOYEE_NAME")
            or _rows(f, "employee")
        ),
        higher_is_better=None,
        decomposable=True,
    ),
    Metric(
        key="total_employee_cost",
        label="Employee cost",
        unit="currency",
        formula="SUM(EMPLOYEE_COMPENSATION + OVERTIME_PAY + INCENTIVE)",
        requires=(("employee", "EMPLOYEE_COMPENSATION"),),
        higher_is_better=False,
        fn=lambda f, _: _sum_any(f, "employee", _PAY_CONCEPTS),
        description="Base pay plus any overtime and incentives present in the data.",
        decomposable=True,
        rankable=False,
    ),
    Metric(
        key="average_salary",
        label="Average salary",
        unit="currency",
        formula="Employee cost / Employees",
        requires=(("employee", "EMPLOYEE_COMPENSATION"),),
        depends_on=("total_employee_cost", "employee_count"),
        higher_is_better=None,
        fn=lambda _, c: _ratio(c["total_employee_cost"], c["employee_count"]),
    ),
    # --- Cost and profit --------------------------------------------------------
    Metric(
        key="total_cogs",
        label="Cost of goods sold",
        unit="currency",
        formula="SUM(COGS) across sales and expense data",
        requires_any=((("sales", "COGS"), ("expense", "COGS")),),
        higher_is_better=False,
        fn=lambda f, _: _sum(f, "sales", "COGS") + _sum(f, "expense", "COGS"),
        decomposable=True,
        rankable=False,
    ),
    Metric(
        key="total_operating_expense",
        label="Operating expenses",
        unit="currency",
        formula="SUM(OPERATING_EXPENSE)",
        requires=(("expense", "OPERATING_EXPENSE"),),
        higher_is_better=False,
        fn=lambda f, _: _sum(f, "expense", "OPERATING_EXPENSE"),
        decomposable=True,
        rankable=False,
    ),
    Metric(
        key="gross_profit",
        label="Gross profit",
        unit="currency",
        formula="Total revenue - Cost of goods sold",
        depends_on=("total_revenue", "total_cogs"),
        fn=lambda _, c: c["total_revenue"] - c["total_cogs"],
        decomposable=True,
    ),
    Metric(
        key="operating_profit",
        label="Operating profit",
        unit="currency",
        formula="Total revenue - Cost of goods sold - Employee cost - Operating expenses",
        depends_on=("total_revenue", "total_cogs", "total_employee_cost",
                    "total_operating_expense"),
        fn=lambda _, c: (
            c["total_revenue"]
            - c["total_cogs"]
            - c["total_employee_cost"]
            - c["total_operating_expense"]
        ),
        description="Only produced when revenue and every cost component are present.",
        decomposable=True,
    ),
    Metric(
        key="operating_margin",
        label="Operating margin",
        unit="percent",
        formula="Operating profit / Total revenue x 100",
        depends_on=("operating_profit", "total_revenue"),
        fn=lambda _, c: (
            None
            if not c["total_revenue"]
            else 100 * c["operating_profit"] / c["total_revenue"]
        ),
    ),
    # --- Efficiency -------------------------------------------------------------
    Metric(
        key="employee_cost_ratio",
        label="Employee cost ratio",
        unit="percent",
        formula="Employee cost / Total revenue x 100",
        depends_on=("total_employee_cost", "total_revenue"),
        higher_is_better=False,
        fn=lambda _, c: (
            None
            if not c["total_revenue"]
            else 100 * c["total_employee_cost"] / c["total_revenue"]
        ),
        description="Share of revenue consumed by pay.",
    ),
    Metric(
        key="revenue_per_employee",
        label="Revenue per employee",
        unit="currency",
        formula="Total revenue / Employees",
        depends_on=("total_revenue", "employee_count"),
        fn=lambda _, c: _ratio(c["total_revenue"], c["employee_count"]),
    ),
    Metric(
        key="profit_per_employee",
        label="Profit per employee",
        unit="currency",
        formula="Operating profit / Employees",
        depends_on=("operating_profit", "employee_count"),
        fn=lambda _, c: _ratio(c["operating_profit"], c["employee_count"]),
    ),
    Metric(
        key="average_rating",
        label="Average customer rating",
        unit="ratio",
        formula="MEAN(RATING)",
        requires=(("sales", "RATING"),),
        fn=lambda f, _: (
            float(pd.to_numeric(f["sales"]["RATING"], errors="coerce").mean())
            if "sales" in f and "RATING" in f["sales"].columns
            else None
        ),
    ),
)

METRICS_BY_KEY: dict[str, Metric] = {m.key: m for m in METRICS}

# Headline figures for the company overview card (PRD sec. 27).
HEADLINE_METRICS = (
    "total_revenue",
    "operating_profit",
    "total_employee_cost",
    "total_operating_expense",
    "total_orders",
    "employee_count",
)

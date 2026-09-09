"""Problem detection and driver analysis (PRD sec. 21-23).

Findings are typed so the interface can keep them apart:

* ``fact``       -- a calculated number, stated plainly.
* ``driver``     -- a decomposition the data supports, e.g. which branch
                    contributed most of a company-wide increase.
* ``hypothesis`` -- a possible explanation, explicitly labelled as unproven.

No rule here claims a cause it cannot show. "Employee cost rose faster than
revenue" is a fact about two series; "you over-hired" is not, and is only ever
emitted as a hypothesis.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.analytics.comparison import Change
from app.analytics.engine import MetricResult
from app.analytics.registry import METRICS_BY_KEY

# Below this, a movement is noise rather than a finding.
MATERIAL_PCT = 5.0
DIVERGENCE_PCT = 5.0


@dataclass
class Finding:
    kind: str  # fact | driver | hypothesis
    severity: str  # high | medium | low
    code: str
    title: str
    detail: str
    evidence: dict = field(default_factory=dict)
    metrics: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _by_key(changes: list[Change]) -> dict[str, Change]:
    return {c.key: c for c in changes}


def detect_period_problems(changes: list[Change]) -> list[Finding]:
    """Rules over period-on-period movements."""
    found: list[Finding] = []
    ch = _by_key(changes)

    revenue = ch.get("total_revenue")
    profit = ch.get("operating_profit")
    emp_cost = ch.get("total_employee_cost")
    emp_count = ch.get("employee_count")
    opex = ch.get("total_operating_expense")
    cogs = ch.get("total_cogs")

    # Revenue up while profit falls -- the headline restaurant problem.
    if revenue and profit and revenue.direction == "up" and profit.direction == "down":
        found.append(
            Finding(
                kind="fact",
                severity="high",
                code="revenue_up_profit_down",
                title="Revenue increased but profit declined",
                detail=(
                    f"Revenue rose {revenue.percent:.1f}% while operating profit fell "
                    f"{abs(profit.percent):.1f}%."
                ),
                evidence={"revenue_pct": revenue.percent, "profit_pct": profit.percent},
                metrics=["total_revenue", "operating_profit"],
            )
        )

    # Any cost outgrowing revenue.
    for cost in (emp_cost, opex, cogs):
        if not cost or not revenue or cost.percent is None or revenue.percent is None:
            continue
        if cost.direction == "up" and cost.percent - revenue.percent > DIVERGENCE_PCT:
            found.append(
                Finding(
                    kind="fact",
                    severity="high" if cost.percent - revenue.percent > 10 else "medium",
                    code=f"{cost.key}_outgrowing_revenue",
                    title=f"{cost.label} is growing faster than revenue",
                    detail=(
                        f"{cost.label} rose {cost.percent:.1f}% against revenue growth of "
                        f"{revenue.percent:.1f}%."
                    ),
                    evidence={"cost_pct": cost.percent, "revenue_pct": revenue.percent},
                    metrics=[cost.key, "total_revenue"],
                )
            )

    # Headcount as a supported driver of the pay bill, never asserted as the cause.
    if emp_cost and emp_count and emp_cost.direction == "up" and emp_count.direction == "up":
        found.append(
            Finding(
                kind="driver",
                severity="medium",
                code="headcount_drives_employee_cost",
                title="Headcount grew alongside employee cost",
                detail=(
                    f"Employee cost rose {emp_cost.percent:.1f}% and headcount rose "
                    f"{emp_count.percent:.1f}% over the same period."
                ),
                evidence={"cost_pct": emp_cost.percent, "headcount_pct": emp_count.percent},
                metrics=["total_employee_cost", "employee_count"],
            )
        )
        if emp_cost.percent and emp_count.percent and emp_cost.percent > emp_count.percent + 3:
            found.append(
                Finding(
                    kind="hypothesis",
                    severity="low",
                    code="pay_rate_hypothesis",
                    title="Pay per employee may have risen",
                    detail=(
                        "Employee cost grew faster than headcount, which is consistent with "
                        "higher average pay, more overtime or a changed role mix. The data "
                        "here does not distinguish between them."
                    ),
                    evidence={"cost_pct": emp_cost.percent, "headcount_pct": emp_count.percent},
                    metrics=["total_employee_cost", "employee_count", "average_salary"],
                )
            )

    revenue_down = revenue and revenue.direction == "down" and abs(revenue.percent or 0) >= MATERIAL_PCT
    if revenue_down:
        found.append(
            Finding(
                kind="fact",
                severity="high",
                code="revenue_declined",
                title="Revenue declined",
                detail=f"Revenue fell {abs(revenue.percent):.1f}% against the previous period.",
                evidence={"revenue_pct": revenue.percent},
                metrics=["total_revenue"],
            )
        )

    return found


def detect_branch_problems(comparison: dict) -> list[Finding]:
    """Rules over a single-period branch comparison."""
    found: list[Finding] = []
    rows = {row["key"]: row for row in comparison["metrics"]}

    ratio = rows.get("employee_cost_ratio")
    if ratio and ratio["comparable"] and ratio["ranking"]:
        worst, best = ratio["worst"], ratio["best"]
        gap = ratio["values"][worst] - ratio["values"][best]
        if gap >= DIVERGENCE_PCT:
            found.append(
                Finding(
                    kind="fact",
                    severity="high" if gap >= 10 else "medium",
                    code="employee_cost_ratio_spread",
                    title=f"{worst} spends far more of its revenue on pay than {best}",
                    detail=(
                        f"{worst} spends {ratio['values'][worst]:.1f}% of revenue on employee "
                        f"cost against {ratio['values'][best]:.1f}% at {best}, a gap of "
                        f"{gap:.1f} percentage points."
                    ),
                    evidence={m: ratio["values"][m] for m in (worst, best)},
                    metrics=["employee_cost_ratio"],
                )
            )

    profit = rows.get("operating_profit")
    if profit and profit["comparable"]:
        losers = {b: v for b, v in profit["values"].items() if v < 0}
        if losers:
            found.append(
                Finding(
                    kind="fact",
                    severity="high",
                    code="loss_making_branch",
                    title=f"{len(losers)} branch(es) are operating at a loss",
                    detail="Operating profit is negative at " + ", ".join(sorted(losers)) + ".",
                    evidence=losers,
                    metrics=["operating_profit"],
                )
            )

    return found


def contribution_analysis(
    current: dict[str, dict[str, MetricResult]],
    previous: dict[str, dict[str, MetricResult]],
    metric_key: str,
) -> list[Finding]:
    """Which members drove a company-level movement (PRD sec. 22-23).

    This is a decomposition, not a cause: it reports the share of the total
    change each branch accounts for, and nothing about why.
    """
    meta = METRICS_BY_KEY.get(metric_key)
    if meta is None or not meta.decomposable:
        # Branch shares of a ratio or an average do not sum to the company
        # figure, so there is no contribution to report.
        return []

    deltas: dict[str, float] = {}
    for member, results in current.items():
        cur, prev = results.get(metric_key), previous.get(member, {}).get(metric_key)
        if not cur or not prev or not cur.available or not prev.available:
            continue
        if cur.value is None or prev.value is None:
            continue
        deltas[member] = cur.value - prev.value

    total = sum(deltas.values())
    if not deltas or abs(total) < 1e-9:
        return []

    label = next(
        (r[metric_key].label for r in current.values() if metric_key in r), metric_key
    )
    top, top_delta = max(deltas.items(), key=lambda kv: abs(kv[1]))
    share = 100 * top_delta / total

    findings = [
        Finding(
            kind="driver",
            severity="medium",
            code=f"{metric_key}_contribution",
            title=f"{top} accounts for most of the change in {label.lower()}",
            detail=(
                f"{top} contributed {share:.0f}% of the total change in {label.lower()} "
                f"({top_delta:+,.0f} of {total:+,.0f})."
            ),
            evidence={"contributions": {k: round(v, 2) for k, v in deltas.items()},
                      "total_change": round(total, 2)},
            metrics=[metric_key],
        )
    ]

    # A member moving against the aggregate is worth surfacing on its own.
    opposing = {k: v for k, v in deltas.items() if v * total < 0}
    if opposing:
        findings.append(
            Finding(
                kind="driver",
                severity="low",
                code=f"{metric_key}_divergent_members",
                title=f"Some branches moved against the company trend in {label.lower()}",
                detail=", ".join(f"{k} ({v:+,.0f})" for k, v in sorted(opposing.items())) + ".",
                evidence={"contributions": {k: round(v, 2) for k, v in opposing.items()}},
                metrics=[metric_key],
            )
        )
    return findings

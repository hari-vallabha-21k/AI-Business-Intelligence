"""Natural-language Q&A (PRD sec. 28).

    question -> intent -> entity/metric resolution -> scope -> availability check
    -> plan -> deterministic calculation -> validation -> evidence -> explanation

Every step before the explanation is deterministic Python. The language model
sees the finished evidence and writes prose about it; it never picks the
numbers, and it is never asked a question the data cannot answer -- when a
required metric is unavailable the pipeline says so and stops (PRD sec. 33).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.analytics.comparison import compare_dimension, compare_metrics
from app.analytics.engine import Availability, MetricResult, evaluate
from app.analytics.problems import contribution_analysis, detect_period_problems
from app.analytics.provenance import build as build_provenance
from app.analytics.registry import METRICS, METRICS_BY_KEY
from app.analytics.engine import split_by
from app.models import Business
from app.services.layer import load_data
from app.semantic.resolution import signature

# --- Intent -------------------------------------------------------------------

METRIC_LOOKUP = "metric_lookup"
RANKING = "ranking"
COMPARISON = "comparison"
PERIOD_CHANGE = "period_change"
DRIVER = "driver"
UNKNOWN = "unknown"

_WHY = re.compile(r"\b(why|reason|caused|because|driving|driver)\b", re.I)
_RANK = re.compile(r"\b(best|worst|top|bottom|highest|lowest|which branch|which department|"
                   r"ranking|rank|performing)\b", re.I)
_COMPARE = re.compile(r"\b(compare|versus|vs\.?|against|difference between|better than|"
                      r"worse than)\b", re.I)
_CHANGE = re.compile(r"\b(change[d]?|last month|previous|month on month|grew|fell|drop|"
                     r"decline|increase|decrease|trend)\b", re.I)

# Words that point at a metric. Ordered so that the most specific wins.
_METRIC_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("employee_cost_ratio", ("employee cost ratio", "salary to revenue", "labour ratio",
                             "labor ratio", "staff cost ratio")),
    ("total_employee_cost", ("employee cost", "salary", "salaries", "payroll", "wage",
                             "staff cost", "labour cost", "labor cost", "spending on staff",
                             "spending on employees")),
    ("employee_count", ("headcount", "how many employees", "number of employees", "staff count")),
    ("average_salary", ("average salary", "average pay", "mean salary")),
    # More specific phrases first: "gross profit margin" must resolve to gross
    # profit, not to the generic "profit".
    ("gross_profit", ("gross profit", "gross margin")),
    ("operating_profit", ("profit", "profitable", "profitability", "bottom line")),
    ("operating_margin", ("margin", "profit margin")),
    ("total_operating_expense", ("operating expense", "expenses", "overheads", "opex",
                                 "running cost")),
    ("total_cogs", ("cogs", "cost of goods", "food cost", "material cost")),
    ("total_discount", ("discount", "discounts")),
    ("total_orders", ("orders", "transactions", "bills", "covers")),
    ("average_order_value", ("average order", "average bill", "average ticket", "aov")),
    ("revenue_per_employee", ("revenue per employee", "sales per employee")),
    ("total_revenue", ("revenue", "sales", "turnover", "income", "takings")),
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


@dataclass
class Question:
    """What the user asked, as the system understood it."""

    text: str
    intent: str
    metrics: list[str] = field(default_factory=list)
    branches: list[str] = field(default_factory=list)
    period: tuple[date, date] | None = None
    compare_period: tuple[date, date] | None = None
    unresolved: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "intent": self.intent,
            "metrics": self.metrics,
            "branches": self.branches,
            "period": [d.isoformat() for d in self.period] if self.period else None,
            "compare_period": [d.isoformat() for d in self.compare_period]
            if self.compare_period
            else None,
            "unresolved": self.unresolved,
        }


@dataclass
class Answer:
    """The complete result: what was asked, what was computed, what it means."""

    question: Question
    status: str  # answered | unavailable | not_understood
    headline: str
    evidence: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    explanation: str = ""
    interpreter: str = "none"

    def as_dict(self) -> dict:
        return {
            "question": self.question.as_dict(),
            "status": self.status,
            "headline": self.headline,
            "evidence": self.evidence,
            "findings": self.findings,
            "limitations": self.limitations,
            "explanation": self.explanation,
            "interpreter": self.interpreter,
        }


def detect_intent(text: str) -> str:
    if _WHY.search(text):
        return DRIVER
    if _COMPARE.search(text):
        return COMPARISON
    if _RANK.search(text):
        return RANKING
    if _CHANGE.search(text):
        return PERIOD_CHANGE
    return METRIC_LOOKUP


def resolve_metrics(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for key, phrases in _METRIC_WORDS:
        if any(phrase in lowered for phrase in phrases) and key not in found:
            found.append(key)
    return found


# A branch signature shorter than this cannot be matched in free text: "Branch A"
# reduces to "a", which would otherwise match every question ever asked.
MIN_BRANCH_SIGNATURE = 3


def resolve_branches(text: str, known: list[str]) -> list[str]:
    """Match branch names mentioned in the question against real branches.

    Matching is on whole words. A bare substring test would find "a" inside
    "total", and scope the whole answer to the wrong branch.
    """
    lowered = text.lower()
    matched = []
    for name in known:
        sig = signature(name)
        if len(sig) < MIN_BRANCH_SIGNATURE:
            continue
        if re.search(rf"\b{re.escape(sig)}\b", lowered):
            matched.append(name)
    return matched


def resolve_period(text: str, default_year: int | None = None) -> tuple[date, date] | None:
    """Understand 'March', 'March 2026', '2026' or an explicit ISO range."""
    lowered = text.lower()

    explicit = re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", lowered)
    if len(explicit) >= 2:
        first = date(*(int(p) for p in explicit[0]))
        second = date(*(int(p) for p in explicit[1]))
        return (min(first, second), max(first, second))

    year_match = re.search(r"\b(20\d{2})\b", lowered)
    year = int(year_match.group(1)) if year_match else default_year

    for name, number in _MONTHS.items():
        if name in lowered and year:
            start = date(year, number, 1)
            end = (
                date(year + 1, 1, 1) if number == 12 else date(year, number + 1, 1)
            )
            return (start, date.fromordinal(end.toordinal() - 1))

    if year_match:
        return (date(year, 1, 1), date(year, 12, 31))
    return None


def previous_period(period: tuple[date, date]) -> tuple[date, date]:
    """The comparable period immediately before this one."""
    start, end = period
    if start.day == 1 and (end.month != start.month or end.year != start.year or True):
        month = start.month - 1 or 12
        year = start.year - (1 if start.month == 1 else 0)
        previous_start = date(year, month, 1)
        next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        return (previous_start, date.fromordinal(next_month.toordinal() - 1))
    span = (end - start).days + 1
    return (date.fromordinal(start.toordinal() - span), date.fromordinal(start.toordinal() - 1))


def understand(text: str, known_branches: list[str], default_year: int | None) -> Question:
    """Turn the raw question into a resolved, checkable request."""
    intent = detect_intent(text)
    metrics = resolve_metrics(text)
    branches = resolve_branches(text, known_branches)
    period = resolve_period(text, default_year)

    unresolved = []
    if not metrics and intent in (METRIC_LOOKUP, DRIVER):
        unresolved.append("which figure you mean")

    compare = previous_period(period) if period and intent in (DRIVER, PERIOD_CHANGE) else None
    return Question(
        text=text,
        intent=intent,
        metrics=metrics,
        branches=branches,
        period=period,
        compare_period=compare,
        unresolved=unresolved,
    )


# --- Execution ----------------------------------------------------------------


def _evidence_row(result: MetricResult, scope: str = "All branches") -> dict:
    row = result.as_dict()
    row["scope"] = scope
    return row


def _describe(result: MetricResult, currency: str) -> str:
    if result.value is None:
        return f"{result.label} is not available"
    if result.unit == "percent":
        return f"{result.label} is {result.value:.1f}%"
    if result.unit == "count":
        return f"{result.label} is {result.value:,.0f}"
    return f"{result.label} is {currency} {result.value:,.0f}"


def answer(
    db: Session, business: Business, text: str, interpreter=None
) -> Answer:
    """Run the whole pipeline for one question."""
    from app.ai.interpreter import get_interpreter

    interpreter = interpreter or get_interpreter()
    branches = [b.name for b in business.branches]

    # The default year comes from the data, not from today's date: a question
    # about "March" means March of the data the user actually uploaded.
    all_data = load_data(db, business.id)
    years = [v.period_start.year for v in all_data.versions if v.period_start]
    question = understand(text, branches, max(years) if years else None)

    if question.unresolved:
        return Answer(
            question=question,
            status="not_understood",
            headline="I need a little more detail.",
            limitations=[
                "I could not tell " + " or ".join(question.unresolved) + "."
            ],
            explanation=(
                "Try naming the figure you want — for example revenue, employee cost, "
                "profit or orders."
            ),
        )

    period = question.period
    loaded = load_data(
        db, business.id, question.branches or None,
        period[0] if period else None, period[1] if period else None,
    )
    if not loaded.frames:
        return Answer(
            question=question,
            status="unavailable",
            headline="There is no data for that selection.",
            limitations=loaded.notes or ["No uploaded data matches that period or branch."],
            explanation=(
                "Upload data covering that period, or ask about a period you have "
                "already uploaded."
            ),
        )

    quality, sources = build_provenance(loaded.versions, loaded.frames)
    results = evaluate(loaded.frames, quality=quality, sources=sources)
    currency = business.currency

    handlers = {
        RANKING: _answer_ranking,
        COMPARISON: _answer_comparison,
        PERIOD_CHANGE: _answer_change,
        DRIVER: _answer_change,
        METRIC_LOOKUP: _answer_lookup,
    }
    result = handlers.get(question.intent, _answer_lookup)(
        db, business, question, loaded, results, currency
    )

    if result.status == "answered":
        result.explanation = interpreter.explain(result)
        result.interpreter = interpreter.name
    return result


def _unavailable_answer(question: Question, results: dict, metric_keys: list[str]) -> Answer | None:
    """Refuse rather than invent when a requested metric cannot be computed."""
    blocked = [
        results[key]
        for key in metric_keys
        if key in results and results[key].availability is Availability.UNAVAILABLE
    ]
    if not blocked:
        return None
    return Answer(
        question=question,
        status="unavailable",
        headline=f"I can't calculate {blocked[0].label.lower()} from the data you've uploaded.",
        limitations=[r.reason for r in blocked if r.reason],
        explanation=(
            f"{blocked[0].reason} Upload the missing information and I will be able to "
            "answer this."
        ),
    )


def _answer_lookup(db, business, question, loaded, results, currency) -> Answer:
    keys = question.metrics or ["total_revenue"]
    refusal = _unavailable_answer(question, results, keys)
    if refusal:
        return refusal

    scope = ", ".join(question.branches) if question.branches else "All branches"
    evidence = [_evidence_row(results[k], scope) for k in keys if k in results]
    headline = "; ".join(_describe(results[k], currency) for k in keys if k in results)
    return Answer(
        question=question,
        status="answered",
        headline=headline,
        evidence=evidence,
        limitations=_limitations(evidence),
    )


def _answer_ranking(db, business, question, loaded, results, currency) -> Answer:
    keys = question.metrics or ["total_revenue"]
    refusal = _unavailable_answer(question, results, keys)
    if refusal:
        return refusal

    comparison = compare_dimension(loaded.frames, "BRANCH")
    if len(comparison["members"]) < 2:
        return Answer(
            question=question,
            status="unavailable",
            headline="There is only one branch with data, so there is nothing to rank.",
            limitations=["Branch comparison needs at least two branches."],
        )

    rows = [row for row in comparison["metrics"] if row["key"] in keys]
    ranked = [row for row in rows if row["ranking"]]
    if not ranked:
        blocked = rows[0] if rows else None
        return Answer(
            question=question,
            status="unavailable",
            headline="I can't rank the branches on that figure.",
            limitations=[blocked["note"]] if blocked and blocked.get("note") else
            ["That figure is not comparable across branches."],
        )

    top = ranked[0]
    headline = f"{top['best']} leads on {top['label'].lower()}."
    evidence = [
        {
            "label": row["label"],
            "unit": row["unit"],
            "values": row["values"],
            "best": row["best"],
            "worst": row["worst"],
            "scope": "By branch",
        }
        for row in ranked
    ]
    return Answer(
        question=question,
        status="answered",
        headline=headline,
        evidence=evidence,
        findings=comparison.get("findings", []),
        limitations=[row["note"] for row in rows if row.get("note")],
    )


def _answer_comparison(db, business, question, loaded, results, currency) -> Answer:
    if len(question.branches) < 2:
        return _answer_ranking(db, business, question, loaded, results, currency)

    keys = question.metrics or ["total_revenue", "operating_profit", "employee_cost_ratio"]
    comparison = compare_dimension(loaded.frames, "BRANCH")
    rows = [
        row for row in comparison["metrics"]
        if row["key"] in keys and set(question.branches) <= set(row["values"])
    ]
    if not rows:
        return Answer(
            question=question,
            status="unavailable",
            headline="I can't compare those branches on that figure.",
            limitations=["The figure is not available for both branches."],
        )

    first, second = question.branches[0], question.branches[1]
    lead = rows[0]
    difference = lead["values"][first] - lead["values"][second]
    headline = (
        f"{first} is {'ahead of' if difference > 0 else 'behind'} {second} on "
        f"{lead['label'].lower()}."
    )
    evidence = [
        {
            "label": row["label"],
            "unit": row["unit"],
            "values": {b: row["values"][b] for b in question.branches},
            "scope": " vs ".join(question.branches),
        }
        for row in rows
    ]
    return Answer(question=question, status="answered", headline=headline, evidence=evidence,
                  findings=comparison.get("findings", []))


def _answer_change(db, business, question, loaded, results, currency) -> Answer:
    # If the user named a figure we cannot compute, say so rather than
    # answering about a different one (Rule 2, PRD sec. 33).
    refusal = _unavailable_answer(question, results, question.metrics)
    if refusal:
        return refusal

    if not question.compare_period:
        return Answer(
            question=question,
            status="not_understood",
            headline="I need to know which period to compare.",
            limitations=["Name a month or a date range, for example 'March 2026'."],
        )

    previous = load_data(
        db, business.id, question.branches or None,
        question.compare_period[0], question.compare_period[1],
    )
    if not previous.frames:
        return Answer(
            question=question,
            status="unavailable",
            headline="There is no earlier period to compare against.",
            limitations=[
                f"No data was found for "
                f"{question.compare_period[0]} to {question.compare_period[1]}."
            ],
        )

    previous_results = evaluate(previous.frames)
    changes = compare_metrics(results, previous_results)
    if question.metrics:
        focus = [c for c in changes if c.key in question.metrics] or changes
    else:
        focus = changes

    findings = [f.as_dict() for f in detect_period_problems(changes)]

    # Decompose the movement by branch -- deterministically, and only for
    # metrics where a branch share is a meaningful thing to compute.
    current_by_branch = {n: evaluate(f) for n, f in split_by(loaded.frames, "BRANCH").items()}
    previous_by_branch = {n: evaluate(f) for n, f in split_by(previous.frames, "BRANCH").items()}
    drivers = []
    for change in focus[:4]:
        drivers.extend(
            f.as_dict()
            for f in contribution_analysis(current_by_branch, previous_by_branch, change.key)
        )

    lead = focus[0] if focus else None
    headline = (
        f"{lead.label} {'rose' if lead.direction == 'up' else 'fell'} "
        f"{abs(lead.percent):.1f}%." if lead and lead.percent is not None
        else "Nothing changed materially between those periods."
    )
    return Answer(
        question=question,
        status="answered",
        headline=headline,
        evidence=[c.as_dict() | {"scope": "Period over period"} for c in focus],
        findings=findings + drivers,
        limitations=loaded.notes + previous.notes,
    )


def _limitations(evidence: list[dict]) -> list[str]:
    out: list[str] = []
    for row in evidence:
        out.extend(row.get("caveats", []) or [])
    return sorted(set(out))

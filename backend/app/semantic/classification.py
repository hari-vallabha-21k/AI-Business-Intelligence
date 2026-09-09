"""Dataset classification: what kind of business data is this file? (PRD sec. 8)

Classification never rests on the filename alone -- a file called ``Sales.xlsx``
routinely contains payroll. The filename is one weak signal among several; the
columns that were actually mapped are the strong one.

Every classification carries a confidence and the reasons behind it, and a weak
result is flagged for review rather than acted on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.semantic.engine import MEDIUM_THRESHOLD, MappingProposal

# Categories the analytics layer knows how to consume, plus the finer
# distinctions that matter for grain (an invoice is not an invoice line).
CATEGORIES = (
    "sales_transaction",
    "invoice",
    "invoice_item",
    "employees",
    "payroll",
    "attendance",
    "expenses",
    "products",
    "inventory",
    "branches",
    "customers",
    "departments",
    "suppliers",
    "unknown",
)

# How each category maps onto the analytical entity kinds the metric registry
# uses. Several categories collapse: payroll and employees both feed employee
# cost, but they are distinguished here because their grain differs.
ENTITY_KIND = {
    "sales_transaction": "sales",
    "invoice": "sales",
    "invoice_item": "sales",
    "employees": "employee",
    "payroll": "employee",
    "attendance": "employee",
    "expenses": "expense",
    "products": "reference",
    "inventory": "reference",
    "branches": "reference",
    "customers": "reference",
    "departments": "reference",
    "suppliers": "reference",
    "unknown": "unknown",
}

# Concepts that vote for a category, and how strongly.
_SIGNALS: dict[str, dict[str, float]] = {
    "sales_transaction": {"REVENUE": 3.0, "ORDER_ID": 2.0, "QUANTITY": 1.0, "PRODUCT": 1.0,
                          "DISCOUNT": 1.0, "CHANNEL": 1.0, "CUSTOMER_ID": 1.0, "TAX": 0.5},
    "invoice": {"ORDER_ID": 3.0, "REVENUE": 2.0, "TAX": 1.0, "CUSTOMER_ID": 1.0},
    "invoice_item": {"ORDER_ID": 2.0, "PRODUCT": 3.0, "QUANTITY": 2.0, "REVENUE": 1.0},
    "employees": {"EMPLOYEE_ID": 3.0, "EMPLOYEE_NAME": 2.0, "ROLE": 2.0, "DEPARTMENT": 1.5},
    "payroll": {"EMPLOYEE_COMPENSATION": 3.0, "EMPLOYEE_ID": 2.0, "OVERTIME_PAY": 2.0,
                "INCENTIVE": 1.5},
    "attendance": {"ATTENDANCE_DAYS": 3.0, "EMPLOYEE_ID": 2.0, "DATE": 1.5},
    "expenses": {"OPERATING_EXPENSE": 3.0, "EXPENSE_CATEGORY": 2.5, "COGS": 1.5},
    "products": {"PRODUCT": 3.0, "CATEGORY": 2.0},
    "branches": {"BRANCH": 3.0},
    "customers": {"CUSTOMER_ID": 3.0},
    "departments": {"DEPARTMENT": 3.0},
}

# Filename and sheet-name hints. Weak on purpose: they nudge between close
# categories, they do not decide.
_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "sales_transaction": ("sales", "revenue", "transaction", "txn", "orders", "billing", "pos"),
    "invoice": ("invoice", "bill", "invoices"),
    "invoice_item": ("item", "line", "detail", "invoice_item", "lineitem"),
    "employees": ("employee", "staff", "team", "hr", "headcount", "roster"),
    "payroll": ("payroll", "salary", "salaries", "wages", "compensation", "pay"),
    "attendance": ("attendance", "shift", "roster", "timesheet", "hours"),
    "expenses": ("expense", "expenses", "cost", "costs", "opex", "overhead", "spend"),
    "products": ("product", "menu", "item_master", "catalog", "sku"),
    "inventory": ("inventory", "stock", "godown", "warehouse"),
    "branches": ("branch", "branches", "store", "stores", "outlet", "location"),
    "customers": ("customer", "customers", "guest", "client"),
    "departments": ("department", "departments", "dept"),
    "suppliers": ("supplier", "vendor", "purchase"),
}

# Score at which a category is considered well evidenced -- roughly two strong
# column signals.
STRONG_EVIDENCE = 5.0
NAME_WEIGHT = 1.2
GRAIN_WEIGHT = 1.5
HIGH_CONFIDENCE = 0.70
REVIEW_THRESHOLD = 0.45

_TOKENS = re.compile(r"[^a-z0-9]+")


@dataclass
class Classification:
    category: str
    confidence: float
    entity_kind: str
    reasons: list[str] = field(default_factory=list)
    alternatives: list[tuple[str, float]] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return self.confidence < HIGH_CONFIDENCE or self.category == "unknown"

    def as_dict(self) -> dict:
        return {
            "category": self.category,
            "confidence": round(self.confidence, 3),
            "entity_kind": self.entity_kind,
            "needs_review": self.needs_review,
            "reasons": self.reasons,
            "alternatives": [{"category": c, "confidence": round(s, 3)}
                             for c, s in self.alternatives],
        }


def _name_tokens(*names: str | None) -> set[str]:
    tokens: set[str] = set()
    for name in names:
        if name:
            tokens |= {t for t in _TOKENS.split(name.lower()) if t}
    return tokens


def classify(
    proposals: list[MappingProposal],
    filename: str | None = None,
    sheet_name: str | None = None,
    grain_keys: tuple[str, ...] = (),
) -> Classification:
    """Score every category from the mapped columns, the name and the grain."""
    mapped = {p.concept for p in proposals if p.concept and p.score >= MEDIUM_THRESHOLD}
    tokens = _name_tokens(filename, sheet_name)

    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    for category, signals in _SIGNALS.items():
        score = 0.0
        hits = []
        for concept, weight in signals.items():
            if concept in mapped:
                score += weight
                hits.append(concept)
        if hits:
            reasons.setdefault(category, []).append(
                f"columns identified as {', '.join(sorted(hits))}"
            )
        scores[category] = score

    for category, hints in _NAME_HINTS.items():
        if tokens & set(hints):
            scores[category] = scores.get(category, 0.0) + NAME_WEIGHT
            reasons.setdefault(category, []).append("the file or sheet name suggests it")

    # Grain settles the invoice/line-item question, which column names cannot:
    # both tables carry an order id, only the line table repeats it.
    keys = set(grain_keys)
    if keys:
        if keys == {"ORDER_ID"}:
            scores["invoice"] = scores.get("invoice", 0) + GRAIN_WEIGHT
            scores["sales_transaction"] = scores.get("sales_transaction", 0) + GRAIN_WEIGHT
            reasons.setdefault("invoice", []).append("one row per order")
        elif "ORDER_ID" in keys and keys & {"PRODUCT", "CATEGORY"}:
            scores["invoice_item"] = scores.get("invoice_item", 0) + GRAIN_WEIGHT * 2
            reasons.setdefault("invoice_item", []).append(
                "several product rows share one order"
            )
        elif "ORDER_ID" in keys:
            # An order id that needs a date to be unique usually means repeated
            # or reversed rows, not line items.
            scores["sales_transaction"] = scores.get("sales_transaction", 0) + GRAIN_WEIGHT
            reasons.setdefault("sales_transaction", []).append("one row per order")
        if keys == {"EMPLOYEE_ID"}:
            scores["employees"] = scores.get("employees", 0) + GRAIN_WEIGHT
            scores["payroll"] = scores.get("payroll", 0) + GRAIN_WEIGHT * 0.5
            reasons.setdefault("employees", []).append("one row per employee")
        elif "EMPLOYEE_ID" in keys and "DATE" in keys:
            scores["attendance"] = scores.get("attendance", 0) + GRAIN_WEIGHT * 2
            reasons.setdefault("attendance", []).append("one row per employee per day")

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_category, top_score = ranked[0]
    if top_score <= 0:
        return Classification("unknown", 0.0, "unknown",
                              ["no column matched a known business concept"])

    # Confidence has two parts.
    #
    # Coverage: how much of what this category looks for was actually found.
    # Separation: how far ahead the winner is of the best category that would
    # route the data somewhere *different*. Sibling categories are excluded
    # from that comparison -- invoice and sales_transaction disagree about
    # grain, not about being sales, so their overlap is not uncertainty about
    # what the file is. Within-kind ambiguity is reported in `alternatives`.
    # Coverage asks "did we find enough evidence", not "did we find every
    # signal this category could ever show". A minimal sales file with an id
    # and an amount is still clearly a sales file, even without discount, tax,
    # channel and customer columns.
    coverage = min(top_score / STRONG_EVIDENCE, 1.0)

    top_kind = ENTITY_KIND.get(top_category, "unknown")
    rival = max(
        (score for category, score in ranked[1:] if ENTITY_KIND.get(category) != top_kind),
        default=0.0,
    )
    separation = (top_score - rival) / top_score if top_score else 0.0
    confidence = 0.55 * coverage + 0.45 * max(separation, 0.0)

    # A weakly evidenced guess is still used, but flagged: the data stays
    # usable and every metric derived from it is marked NEEDS_CONFIRMATION
    # rather than being silently trusted (PRD sec. 18, sec. 32). Only a file
    # with no recognised concept at all is left unclassified.
    category = top_category
    return Classification(
        category=category,
        confidence=round(min(confidence, 0.99), 3),
        entity_kind=ENTITY_KIND.get(category, "unknown"),
        reasons=reasons.get(top_category, []),
        # Relative strength of the runners-up, on the winner's scale.
        alternatives=[(c, round(min(s / top_score, 1.0), 3))
                      for c, s in ranked[1:4] if s > 0],
    )

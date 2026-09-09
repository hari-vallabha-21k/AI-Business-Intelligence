"""Canonical business concepts (PRD sec. 13).

Column names vary between businesses and between months. Everything downstream
-- analytics, comparison, problem detection -- speaks only in the concepts
defined here, so ``food_sales`` in January and ``food_revenue`` in February
produce the same metric.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    DIMENSION = "dimension"
    MEASURE = "measure"
    IDENTIFIER = "identifier"
    TEMPORAL = "temporal"


@dataclass(frozen=True)
class Concept:
    name: str
    role: Role
    label: str
    synonyms: tuple[str, ...] = ()
    # Concepts only proposed for datasets of these kinds ("" = any).
    entity_hints: tuple[str, ...] = ()
    additive: bool = False
    description: str = ""
    value_hints: tuple[str, ...] = field(default=(), repr=False)


# --- Dimensions and identifiers -------------------------------------------------

_CONCEPTS: tuple[Concept, ...] = (
    Concept(
        "BRANCH",
        Role.DIMENSION,
        "Branch",
        ("branch", "branch_name", "location", "store", "outlet", "site", "unit", "restaurant"),
        description="Physical location the row belongs to.",
    ),
    Concept(
        "DEPARTMENT",
        Role.DIMENSION,
        "Department",
        ("department", "dept", "team", "section", "division", "function"),
    ),
    Concept(
        "ROLE",
        Role.DIMENSION,
        "Role",
        ("role", "designation", "position", "job_title", "title", "grade"),
        entity_hints=("employee",),
    ),
    Concept(
        "EMPLOYEE_ID",
        Role.IDENTIFIER,
        "Employee ID",
        ("employee_id", "emp_id", "staff_id", "empid", "employee_code", "payroll_id"),
        entity_hints=("employee",),
    ),
    Concept(
        "EMPLOYEE_NAME",
        Role.DIMENSION,
        "Employee name",
        ("employee_name", "emp_name", "staff_name", "name", "full_name"),
        entity_hints=("employee",),
    ),
    Concept(
        "PRODUCT",
        Role.DIMENSION,
        "Product",
        ("product", "item", "item_name", "dish", "sku", "menu_item", "product_name"),
        entity_hints=("sales",),
    ),
    Concept(
        "CATEGORY",
        Role.DIMENSION,
        "Category",
        ("category", "item_category", "product_category", "group", "menu_category", "cuisine"),
    ),
    Concept(
        "CUSTOMER_ID",
        Role.IDENTIFIER,
        "Customer",
        ("customer_id", "cust_id", "customer", "customer_code", "guest_id"),
        entity_hints=("sales",),
    ),
    Concept(
        "ORDER_ID",
        Role.IDENTIFIER,
        "Order",
        ("order_id", "bill_no", "bill_number", "invoice_no", "invoice_id", "ticket_id", "order_no"),
        entity_hints=("sales",),
    ),
    Concept(
        "CHANNEL",
        Role.DIMENSION,
        "Sales channel",
        ("channel", "sales_channel", "order_type", "source", "platform", "mode"),
        entity_hints=("sales",),
    ),
    Concept(
        "EXPENSE_CATEGORY",
        Role.DIMENSION,
        "Expense category",
        ("expense_category", "expense_type", "cost_type", "head", "expense_head", "cost_category"),
        entity_hints=("expense",),
    ),
    Concept(
        "DATE",
        Role.TEMPORAL,
        "Date",
        ("date", "order_date", "transaction_date", "bill_date", "day", "created_at", "period",
         "month", "expense_date", "salary_month", "pay_period"),
    ),
    # --- Measures ---------------------------------------------------------------
    Concept(
        "REVENUE",
        Role.MEASURE,
        "Revenue",
        ("revenue", "sales", "total_sales", "sales_amount", "food_sales", "food_revenue",
         "net_sales", "gross_sales", "amount", "bill_amount", "total", "turnover", "sale_value"),
        entity_hints=("sales",),
        additive=True,
        description="Money billed to customers before or after tax depending on source.",
    ),
    Concept(
        "QUANTITY",
        Role.MEASURE,
        "Quantity",
        ("quantity", "qty", "units", "count", "no_of_items", "item_count", "pcs"),
        entity_hints=("sales",),
        additive=True,
    ),
    Concept(
        "DISCOUNT",
        Role.MEASURE,
        "Discount",
        ("discount", "discount_amount", "promo", "promotion", "offer_amount", "rebate"),
        entity_hints=("sales",),
        additive=True,
    ),
    Concept(
        "TAX",
        Role.MEASURE,
        "Tax",
        ("tax", "gst", "vat", "tax_amount", "sales_tax", "cgst", "sgst"),
        entity_hints=("sales",),
        additive=True,
    ),
    Concept(
        "SERVICE_CHARGE",
        Role.MEASURE,
        "Service charge",
        ("service_charge", "service_fee", "svc_charge", "gratuity"),
        entity_hints=("sales",),
        additive=True,
    ),
    Concept(
        "DELIVERY_FEE",
        Role.MEASURE,
        "Delivery fee",
        ("delivery_fee", "delivery_charge", "shipping", "shipping_fee", "packaging_charge"),
        entity_hints=("sales",),
        additive=True,
    ),
    Concept(
        "COGS",
        Role.MEASURE,
        "Cost of goods sold",
        ("cogs", "cost_of_goods", "food_cost", "material_cost", "purchase_cost", "raw_material",
         "ingredient_cost", "item_cost"),
        additive=True,
    ),
    Concept(
        "OPERATING_EXPENSE",
        Role.MEASURE,
        "Operating expense",
        ("expense", "expenses", "operating_expense", "opex", "cost", "amount_spent",
         "expense_amount", "overhead", "rent", "utilities"),
        entity_hints=("expense",),
        additive=True,
    ),
    Concept(
        "EMPLOYEE_COMPENSATION",
        Role.MEASURE,
        "Employee compensation",
        ("salary", "monthly_salary", "monthly_pay", "pay", "wage", "wages", "ctc", "basic_pay",
         "gross_pay", "compensation", "net_pay", "payroll"),
        entity_hints=("employee",),
        additive=True,
        description="Base pay per employee for the period.",
    ),
    Concept(
        "OVERTIME_PAY",
        Role.MEASURE,
        "Overtime pay",
        ("overtime", "ot_pay", "overtime_pay", "overtime_amount", "extra_hours_pay"),
        entity_hints=("employee",),
        additive=True,
    ),
    Concept(
        "INCENTIVE",
        Role.MEASURE,
        "Incentive",
        ("incentive", "bonus", "commission", "allowance", "tips"),
        entity_hints=("employee",),
        additive=True,
    ),
    Concept(
        "ATTENDANCE_DAYS",
        Role.MEASURE,
        "Days present",
        ("attendance", "days_present", "present_days", "working_days", "days_worked", "shifts"),
        entity_hints=("employee",),
        additive=True,
    ),
    Concept(
        "RATING",
        Role.MEASURE,
        "Customer rating",
        ("rating", "review_score", "customer_rating", "stars", "feedback_score", "nps"),
        entity_hints=("sales",),
    ),
)

CONCEPTS: dict[str, Concept] = {c.name: c for c in _CONCEPTS}

MEASURES = {n for n, c in CONCEPTS.items() if c.role is Role.MEASURE}
DIMENSIONS = {n for n, c in CONCEPTS.items() if c.role is Role.DIMENSION}
IDENTIFIERS = {n for n, c in CONCEPTS.items() if c.role is Role.IDENTIFIER}

# Concepts whose presence identifies what a dataset is about (process doc sec. 5).
ENTITY_SIGNALS: dict[str, tuple[str, ...]] = {
    "employee": ("EMPLOYEE_ID", "EMPLOYEE_NAME", "EMPLOYEE_COMPENSATION", "ROLE",
                 "ATTENDANCE_DAYS", "OVERTIME_PAY"),
    "sales": ("REVENUE", "ORDER_ID", "PRODUCT", "QUANTITY", "DISCOUNT", "CHANNEL", "CUSTOMER_ID"),
    "expense": ("OPERATING_EXPENSE", "EXPENSE_CATEGORY", "COGS"),
}


def concept(name: str) -> Concept | None:
    return CONCEPTS.get(name)


def label(name: str) -> str:
    c = CONCEPTS.get(name)
    return c.label if c else name

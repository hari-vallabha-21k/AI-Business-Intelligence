"""A deliberately messy multi-file business dataset (PRD sec. 37).

Every problem the spec lists is planted here on purpose, so the tests assert
behaviour against data that looks like a real business rather than a clean
demo. The fixtures are deterministic -- same bytes every run -- so failures are
reproducible.

Planted problems, and where:

  sales_jan.xlsx     title rows above the header; column names branch/amount
  sales_feb.csv      renamed columns (store_name/net_sales); a duplicate invoice
  sales_mar.xlsx     renamed again (loc/revenue_amount); refunds; a totals row
  invoice_items.csv  the same March invoices at line-item grain (double-count trap)
  employees.xlsx     inconsistent branch spellings; a transferred employee
  payroll_feb.csv    salary change; one employee with no salary
  payroll_mar.csv    a joiner and a leaver
  expenses.xlsx      expense heads, no COGS
  branches.csv       canonical branch list including an ambiguous abbreviation
  attendance.csv     employee-day grain
"""

from __future__ import annotations

import io

import pandas as pd
from openpyxl import Workbook

BRANCH_SPELLINGS = {
    "Jubilee Hills": ["Jubilee Hills", "jubilee hills", "JUBILEE HILLS", "Jubilee-Hills"],
    "Banjara Hills": ["Banjara Hills", "banjara hills", "Banjara  Hills"],
    "Gachibowli": ["Gachibowli", "gachibowli"],
}


def _spelling(branch: str, index: int) -> str:
    options = BRANCH_SPELLINGS[branch]
    return options[index % len(options)]


def _xlsx(df: pd.DataFrame, title_rows: list[str] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in title_rows or []:
        ws.append([row])
    ws.append(list(df.columns))
    for record in df.itertuples(index=False):
        ws.append(list(record))
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode()


def sales_january() -> bytes:
    """Title rows above the header; dd/mm/yyyy dates; generic 'amount' column."""
    rows = []
    for index in range(60):
        branch = list(BRANCH_SPELLINGS)[index % 3]
        rows.append(
            {
                "bill_no": f"JAN{index:04d}",
                "date": f"{(index % 28) + 1:02d}/01/2026",
                "branch": _spelling(branch, index),
                "item": ["Biryani", "Paneer Tikka", "Naan"][index % 3],
                "qty": (index % 3) + 1,
                "amount": 300 + (index % 5) * 40,
            }
        )
    return _xlsx(
        pd.DataFrame(rows),
        title_rows=["Spice Route Restaurants", "Sales Register - January 2026", ""],
    )


def sales_february() -> bytes:
    """Schema change: store_name/net_sales. Contains one duplicated invoice row."""
    rows = []
    for index in range(60):
        branch = list(BRANCH_SPELLINGS)[index % 3]
        rows.append(
            {
                "invoice_no": f"FEB{index:04d}",
                "txn_date": f"2026-02-{(index % 28) + 1:02d}",
                "store_name": _spelling(branch, index + 1),
                "item_name": ["Biryani", "Paneer Tikka", "Naan"][index % 3],
                "quantity": (index % 3) + 1,
                "net_sales": 310 + (index % 5) * 40,
            }
        )
    rows.append(dict(rows[0]))  # the same invoice submitted twice
    return _csv(pd.DataFrame(rows))


def sales_march() -> bytes:
    """Renamed again; refunds; a grand total row at the bottom."""
    rows = []
    for index in range(60):
        branch = list(BRANCH_SPELLINGS)[index % 3]
        rows.append(
            {
                "receipt_no": f"MAR{index:04d}",
                "bill_date": f"2026-03-{(index % 28) + 1:02d}",
                "loc": _spelling(branch, index + 2),
                "product": ["Biryani", "Paneer Tikka", "Naan"][index % 3],
                "units": (index % 3) + 1,
                "revenue_amount": 320 + (index % 5) * 40,
            }
        )
    # Two refunds, reversing earlier sales and reusing their receipt numbers.
    for index in (3, 17):
        reversal = dict(rows[index])
        reversal["revenue_amount"] = -reversal["revenue_amount"]
        reversal["bill_date"] = "2026-03-28"
        rows.append(reversal)
    frame = pd.DataFrame(rows)
    total = {
        "receipt_no": "TOTAL",
        "revenue_amount": frame["revenue_amount"].sum(),
        "units": frame["units"].sum(),
    }
    return _xlsx(pd.concat([frame, pd.DataFrame([total])], ignore_index=True))


def invoice_items() -> bytes:
    """The same March receipts at line-item grain: the double-counting trap."""
    rows = []
    for index in range(60):
        receipt = f"MAR{index:04d}"
        total = 320 + (index % 5) * 40
        for line in range(2):
            rows.append(
                {
                    "receipt_no": receipt,
                    "line_item": f"{['Biryani', 'Paneer Tikka', 'Naan'][line % 3]}",
                    "line_qty": 1,
                    "line_amount": total / 2,
                    "loc": _spelling(list(BRANCH_SPELLINGS)[index % 3], index),
                }
            )
    return _csv(pd.DataFrame(rows))


def employees() -> bytes:
    """Employee master. Inconsistent spellings; one employee listed twice."""
    rows = []
    for index in range(30):
        branch = list(BRANCH_SPELLINGS)[index % 3]
        rows.append(
            {
                "emp_id": f"E{index:03d}",
                "name": f"Employee {index:03d}",
                "loc": _spelling(branch, index),
                "department": ["Kitchen", "Service", "Admin"][index % 3],
                "designation": ["Mgr", "waiter", "Chef", "cashier"][index % 4],
            }
        )
    rows.append(dict(rows[5]))  # the same employee recorded twice
    return _xlsx(pd.DataFrame(rows))


def payroll(month: str, *, joiner: bool = False, leaver: bool = False,
            raise_for: str | None = None, missing_salary: bool = False) -> bytes:
    """Monthly payroll with joiners, leavers, raises and a missing salary."""
    rows = []
    for index in range(30):
        if leaver and index == 7:
            continue  # this employee has left
        pay = 25000 + (index % 4) * 1500
        if raise_for and f"E{index:03d}" == raise_for:
            pay = int(pay * 1.2)
        record = {
            "employee_code": f"E{index:03d}",
            "salary_month": f"2026-{month}-01",
            "branch_name": _spelling(list(BRANCH_SPELLINGS)[index % 3], index),
            "gross_pay": f"₹{pay:,}",
            "overtime": [0, 0, 1200, 2400][index % 4],
        }
        if missing_salary and index == 11:
            record["gross_pay"] = None
        rows.append(record)
    if joiner:
        rows.append(
            {
                "employee_code": "E900",
                "salary_month": f"2026-{month}-01",
                "branch_name": "Gachibowli",
                "gross_pay": "₹31,000",
                "overtime": 0,
            }
        )
    return _csv(pd.DataFrame(rows))


def employee_transfer() -> bytes:
    """An employee who moved branch mid-quarter, under a third spelling."""
    return _csv(
        pd.DataFrame(
            [
                {
                    "employee_code": "E003",
                    "salary_month": "2026-03-01",
                    "branch_name": "gachibowli",
                    "gross_pay": "₹28,000",
                    "overtime": 0,
                }
            ]
        )
    )


def expenses() -> bytes:
    """Operating expenses only -- no COGS anywhere in the dataset."""
    rows = []
    for month in ("01", "02", "03"):
        for branch in BRANCH_SPELLINGS:
            for head, amount in [("Rent", 180000), ("Electricity", 55000),
                                 ("Marketing", 30000)]:
                rows.append(
                    {
                        "expense_date": f"2026-{month}-05",
                        "outlet": branch,
                        "expense_head": head,
                        "amount_spent": amount,
                    }
                )
    return _xlsx(pd.DataFrame(rows))


def branches() -> bytes:
    """Canonical branch list, including an abbreviation that is ambiguous."""
    return _csv(
        pd.DataFrame(
            [
                {"branch_code": "BR1", "branch_name": "Jubilee Hills", "city": "Hyderabad"},
                {"branch_code": "BR2", "branch_name": "Banjara Hills", "city": "Hyderabad"},
                {"branch_code": "BR3", "branch_name": "Gachibowli", "city": "Hyderabad"},
            ]
        )
    )


def attendance() -> bytes:
    """Employee-day grain -- must not be mistaken for an employee list."""
    rows = []
    for index in range(10):
        for day in range(1, 6):
            rows.append(
                {
                    "emp_id": f"E{index:03d}",
                    "date": f"2026-03-{day:02d}",
                    "days_present": 1,
                    "shift": "morning" if day % 2 else "evening",
                }
            )
    return _csv(pd.DataFrame(rows))


ALL_FILES: dict[str, callable] = {
    "sales_jan.xlsx": sales_january,
    "sales_feb.csv": sales_february,
    "sales_mar.xlsx": sales_march,
    "employees.xlsx": employees,
    "payroll_feb.csv": lambda: payroll("02", missing_salary=True),
    "payroll_mar.csv": lambda: payroll("03", joiner=True, leaver=True, raise_for="E002"),
    "expenses.xlsx": expenses,
    "branches.csv": branches,
    "attendance.csv": attendance,
}

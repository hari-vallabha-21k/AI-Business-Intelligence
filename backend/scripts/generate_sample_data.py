"""Generate sample restaurant data for demos and manual testing.

Deliberately messy: branch names in mixed spellings, currency symbols in the
salary column, a renamed revenue column in February and a new delivery_fee that
did not exist in January.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parents[2] / "sample_data"
BRANCHES = ["Jubilee Hills", "Banjara Hills", "Gachibowli"]
ITEMS = [
    ("Chicken Biryani", "Main Course", 320, 0.38),
    ("Paneer Tikka", "Starters", 260, 0.30),
    ("Butter Naan", "Breads", 60, 0.22),
    ("Gulab Jamun", "Desserts", 90, 0.25),
    ("Masala Chai", "Beverages", 40, 0.18),
]
# Gachibowli is deliberately over-staffed relative to its revenue.
BRANCH_PROFILE = {
    "Jubilee Hills": {"volume": 1.00, "headcount": 24, "avg_pay": 26_000},
    "Banjara Hills": {"volume": 0.82, "headcount": 22, "avg_pay": 25_000},
    "Gachibowli": {"volume": 0.61, "headcount": 26, "avg_pay": 24_500},
}
BRANCH_SPELLINGS = {
    "Jubilee Hills": ["Jubilee Hills", "jubilee hills", "JUBILEE HILLS", "Jubilee-Hills"],
    "Banjara Hills": ["Banjara Hills", "banjara hills", "Banjara  Hills"],
    "Gachibowli": ["Gachibowli", "gachibowli", "GACHIBOWLI"],
}


def sales_file(year: int, month: int, rng: random.Random, *, february_schema: bool) -> pd.DataFrame:
    """One month of transactions. February renames columns and adds delivery fee."""
    start = date(year, month, 1)
    days = (date(year, month + 1, 1) - start).days if month < 12 else 31
    rows = []
    for branch, profile in BRANCH_PROFILE.items():
        # February trades better everywhere, but costs rise faster at Gachibowli.
        growth = 1.0 if not february_schema else (1.12 if branch != "Gachibowli" else 1.04)
        cost_inflation = 1.0 if not february_schema else (1.02 if branch != "Gachibowli" else 1.19)
        for day in range(days):
            current = start + timedelta(days=day)
            # Sized so payroll lands near a realistic 20-30% of revenue.
            orders = int(rng.gauss(250, 30) * profile["volume"] * growth)
            for order in range(max(orders, 20)):
                item, category, price, cost_ratio = rng.choice(ITEMS)
                quantity = rng.randint(1, 3)
                revenue = price * quantity
                row = {
                    "bill_no": f"{branch[:3].upper()}-{current:%Y%m%d}-{order:04d}",
                    "order_date": current.isoformat(),
                    "location": rng.choice(BRANCH_SPELLINGS[branch]),
                    "item": item,
                    "item_category": category,
                    "quantity": quantity,
                    "discount": round(revenue * rng.choice([0, 0, 0.05, 0.10]), 2),
                    "gst": round(revenue * 0.05, 2),
                    "food_cost": round(revenue * cost_ratio * cost_inflation, 2),
                    "channel": rng.choice(["Dine-in", "Takeaway", "Delivery"]),
                }
                if february_schema:
                    row["food_revenue"] = revenue
                    row["delivery_fee"] = 35 if row["channel"] == "Delivery" else 0
                else:
                    row["food_sales"] = revenue
                rows.append(row)
    return pd.DataFrame(rows)


def employee_file(rng: random.Random, *, february: bool) -> pd.DataFrame:
    rows = []
    for branch, profile in BRANCH_PROFILE.items():
        # Gachibowli adds staff in February despite the weakest revenue growth.
        headcount = profile["headcount"] + (4 if february and branch == "Gachibowli" else 0)
        for i in range(headcount):
            role = "Mgr" if i == 0 else rng.choice(
                ["Waiter", "waiter", "Chef", "Cashier", "Cleaner"]
            )
            pay = int(rng.gauss(profile["avg_pay"], 4000))
            rows.append(
                {
                    "emp_id": f"{branch[:3].upper()}{i:03d}",
                    "name": f"Employee {branch[:3].upper()}{i:03d}",
                    "location": rng.choice(BRANCH_SPELLINGS[branch]),
                    "department": rng.choice(["Kitchen", "Service", "Admin"]),
                    "designation": role,
                    "monthly_pay": f"₹{max(pay, 15000):,}",
                    "days_present": rng.randint(22, 30),
                    "overtime": rng.choice([0, 0, 1200, 2400]),
                }
            )
    return pd.DataFrame(rows)


def expense_file(rng: random.Random, *, february: bool) -> pd.DataFrame:
    rows = []
    for branch in BRANCH_PROFILE:
        for head in ["Rent", "Electricity", "Water", "Marketing", "Maintenance", "Licences"]:
            base = {"Rent": 180_000, "Electricity": 60_000, "Water": 12_000,
                    "Marketing": 35_000, "Maintenance": 22_000, "Licences": 9_000}[head]
            amount = base * rng.uniform(0.9, 1.1) * (1.03 if february else 1.0)
            rows.append(
                {
                    "expense_date": f"2026-{'02' if february else '01'}-05",
                    "branch": rng.choice(BRANCH_SPELLINGS[branch]),
                    "expense_head": head,
                    "amount_spent": round(amount, 2),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    rng = random.Random(20260909)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    files = {
        "sales_january.csv": sales_file(2026, 1, rng, february_schema=False),
        "sales_february.csv": sales_file(2026, 2, rng, february_schema=True),
        "employees_january.xlsx": employee_file(rng, february=False),
        "employees_february.xlsx": employee_file(rng, february=True),
        "expenses_january.csv": expense_file(rng, february=False),
        "expenses_february.csv": expense_file(rng, february=True),
    }
    for name, df in files.items():
        path = OUT_DIR / name
        if name.endswith(".xlsx"):
            df.to_excel(path, index=False)
        else:
            df.to_csv(path, index=False)
        print(f"{path.relative_to(OUT_DIR.parent)}: {len(df):,} rows")


if __name__ == "__main__":
    main()

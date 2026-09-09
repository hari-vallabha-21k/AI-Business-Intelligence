"""Run the whole pipeline over the sample data and print the result.

    python scripts/generate_sample_data.py
    python scripts/demo.py

Uploads six messy files through the real API, then prints the company overview,
the branch comparison and the February-vs-January findings.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample_data"
RULE = "=" * 78


def money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f}"


def main() -> None:
    if not SAMPLE_DIR.exists():
        raise SystemExit("Run scripts/generate_sample_data.py first.")

    with TestClient(app) as client:
        token = client.post(
            "/api/auth/register",
            json={"email": "demo@example.com", "password": "demo-password"},
        )
        if token.status_code == 409:
            token = client.post(
                "/api/auth/token",
                data={"username": "demo@example.com", "password": "demo-password"},
            )
        client.headers["Authorization"] = f"Bearer {token.json()['access_token']}"

        business = client.post(
            "/api/businesses", json={"name": "Spice Route", "currency": "INR"}
        ).json()
        bid = business["id"]

        print(RULE)
        print("UPLOADS")
        print(RULE)
        for path in sorted(SAMPLE_DIR.iterdir()):
            # Payroll is a monthly snapshot with no date column, so the period is
            # supplied at upload -- exactly what the UI asks the user for.
            month = "february" if "february" in path.name else "january"
            form = {"dataset_name": path.stem.split("_")[0].title()}
            if "employees" in path.name:
                form["period_start"] = f"2026-{'02' if month == 'february' else '01'}-01"
                form["period_end"] = f"2026-{'02-28' if month == 'february' else '01-31'}"
            with path.open("rb") as handle:
                response = client.post(
                    f"/api/businesses/{bid}/uploads",
                    files={"file": (path.name, handle.read())},
                    data=form,
                )
            if response.status_code != 201:
                print(f"  {path.name}: REJECTED -- {response.json()['detail']}")
                continue
            body = response.json()
            cleaned = sum(e.get("rows_affected", 0) for e in body["cleaning_log"])
            print(
                f"  {path.name:28} {body['entity_kind']:9} "
                f"{body['row_count']:>6,} rows  {body['period_start']} to {body['period_end']}"
            )
            print(
                f"      mapped {sum(1 for m in body['mappings'] if m['concept'])}"
                f"/{len(body['mappings'])} columns, cleaned {cleaned:,} values"
                + (f", NEW: {', '.join(body['new_concepts'])}" if body["new_concepts"] else "")
            )

        print()
        print(RULE)
        print("COMPANY OVERVIEW (all branches, February 2026)")
        print(RULE)
        february = {"period_start": "2026-02-01", "period_end": "2026-02-28"}
        overview = client.get(f"/api/businesses/{bid}/overview", params=february).json()
        for metric in overview["headline"]:
            value = money(metric["value"]) if metric["available"] else "unavailable"
            print(f"  {metric['label']:24} {value:>16}")
        for metric in overview["metrics"].values():
            if metric["available"] and metric["unit"] == "percent":
                print(f"  {metric['label']:24} {metric['value']:>15.1f}%")

        unavailable = [m for m in overview["unavailable"]]
        if unavailable:
            print("\n  Not calculable from the uploaded data:")
            for metric in unavailable[:4]:
                print(f"    - {metric['reason']}")

        print()
        print(RULE)
        print("BRANCH COMPARISON")
        print(RULE)
        comparison = client.get(
            f"/api/businesses/{bid}/compare/branches", params=february
        ).json()
        members = comparison["members"]
        print("  " + "Metric".ljust(24) + "".join(m.rjust(17) for m in members))
        for row in comparison["metrics"]:
            if not row["comparable"] or row["unit"] not in {"currency", "percent", "count"}:
                continue
            cells = "".join(money(row["values"][m]).rjust(17) for m in members)
            print(f"  {row['label']:24}{cells}")
        print()
        for finding in comparison["findings"]:
            print(f"  [{finding['severity'].upper()}] {finding['detail']}")

        print()
        print(RULE)
        print("FEBRUARY vs JANUARY")
        print(RULE)
        periods = client.get(
            f"/api/businesses/{bid}/compare/periods",
            params={
                "current_start": "2026-02-01", "current_end": "2026-02-28",
                "previous_start": "2026-01-01", "previous_end": "2026-01-31",
            },
        ).json()
        for change in periods["changes"]:
            if change["percent"] is None:
                continue
            arrow = {"up": "^", "down": "v", "flat": "-"}[change["direction"]]
            print(
                f"  {change['label']:24} {money(change['previous']):>14} -> "
                f"{money(change['current']):>14}  {arrow}{abs(change['percent']):>6.1f}%"
            )

        print()
        for finding in periods["findings"] + periods["drivers"]:
            print(f"  [{finding['kind'].upper():10}] {finding['title']}")
            print(f"               {finding['detail']}")


if __name__ == "__main__":
    main()

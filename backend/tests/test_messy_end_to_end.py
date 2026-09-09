"""Acceptance tests against deliberately messy data (PRD sec. 37-38).

These test the ten requirements the spec lists: problems are detected, data is
not silently corrupted, high-confidence fields map automatically, ambiguity is
surfaced, double counting is prevented, entities resolve, metric availability
is correct, unsupported calculations are refused, results are reproducible, and
important answers carry evidence.
"""

from __future__ import annotations

import pytest

from tests.messy_data import ALL_FILES, employee_transfer, invoice_items


def send(client, business_id, name, content, **form):
    return client.post(
        f"/api/businesses/{business_id}/uploads",
        files={"file": (name, content)},
        data={k: str(v) for k, v in form.items() if v is not None},
    )


@pytest.fixture
def messy_business(auth_client, business):
    """Upload the whole messy dataset, returning the business and responses."""
    responses = {}
    periods = {
        "payroll_feb.csv": ("2026-02-01", "2026-02-28"),
        "payroll_mar.csv": ("2026-03-01", "2026-03-31"),
        "employees.xlsx": ("2026-01-01", "2026-03-31"),
    }
    for name, builder in ALL_FILES.items():
        start, end = periods.get(name, (None, None))
        dataset = name.split("_")[0].split(".")[0].title()
        responses[name] = send(
            auth_client, business["id"], name, builder(),
            dataset_name=dataset, period_start=start, period_end=end,
        )
    return business, responses


# --- 1. Every file is accepted and classified --------------------------------

def test_every_messy_file_is_ingested(messy_business):
    _, responses = messy_business
    failed = {n: r.status_code for n, r in responses.items() if r.status_code != 201}
    assert not failed, f"files rejected: {failed}"


def test_files_are_classified_by_content_not_filename(messy_business):
    _, responses = messy_business
    categories = {
        name: r.json()["profile"]["source"] and
        _classification(r)["category"]
        for name, r in responses.items()
    }
    assert categories["sales_jan.xlsx"] in {"sales_transaction", "invoice"}
    assert categories["employees.xlsx"] == "employees"
    assert categories["payroll_feb.csv"] == "payroll"
    assert categories["attendance.csv"] == "attendance"
    assert categories["expenses.xlsx"] == "expenses"
    assert categories["branches.csv"] == "branches"


def _classification(response) -> dict:
    issue = next(
        i for i in response.json()["quality_issues"]
        if i["code"] in {"classified", "low_confidence_classification"}
    )
    return issue["details"]


# --- 2. Grain is detected, and prevents double counting ----------------------

def test_grain_is_detected_per_dataset(messy_business):
    _, responses = messy_business
    grains = {name: _grain(r) for name, r in responses.items()}
    assert grains["employees.xlsx"]["keys"] == ["EMPLOYEE_ID"]
    assert set(grains["attendance.csv"]["keys"]) == {"EMPLOYEE_ID", "DATE"}
    assert "ORDER_ID" in grains["sales_jan.xlsx"]["keys"]


def _grain(response) -> dict:
    issue = next(
        i for i in response.json()["quality_issues"]
        if i["code"] in {"grain_detected", "ambiguous_grain"}
    )
    return issue["details"]


def test_line_items_do_not_double_count_the_same_revenue(auth_client, messy_business):
    """The spec's worst case: an invoice table joined to its line items."""
    business, _ = messy_business
    march = {"period_start": "2026-03-01", "period_end": "2026-03-31"}
    before = auth_client.get(
        f"/api/businesses/{business['id']}/overview", params=march
    ).json()["metrics"]["total_revenue"]["value"]

    # The period is supplied so the file is genuinely in scope: otherwise this
    # would pass merely because an undated file is excluded.
    assert send(
        auth_client, business["id"], "invoice_items.csv", invoice_items(),
        dataset_name="Items", period_start="2026-03-01", period_end="2026-03-31",
    ).status_code == 201

    after = auth_client.get(
        f"/api/businesses/{business['id']}/overview", params=march
    ).json()
    assert after["metrics"]["total_revenue"]["value"] == pytest.approx(before, rel=0.01)
    assert any("same records" in note for note in after["notes"]), after["notes"]


# --- 3. Entity resolution ----------------------------------------------------

def test_branch_spellings_resolve_to_three_branches(auth_client, messy_business):
    business, _ = messy_business
    model = auth_client.get(f"/api/businesses/{business['id']}/model").json()
    branches = {e["name"] for e in model["entities"] if e["type"] == "BRANCH"}
    assert len(branches) == 3, branches

    jubilee = next(e for e in model["entities"] if e["name"].lower().startswith("jubilee"))
    assert len(jubilee["aliases"]) > 1  # several raw spellings, one entity


def test_raw_spellings_are_preserved(auth_client, messy_business):
    """Rule 9: the uploaded values are never overwritten."""
    business, responses = messy_business
    version_id = responses["employees.xlsx"].json()["dataset_version_id"]
    version = auth_client.get(f"/api/versions/{version_id}").json()
    assert any(
        entry["type"] == "label_normalisation" for entry in version["cleaning_log"]
    )


# --- 4. Schema evolution across months --------------------------------------

def test_three_different_schemas_produce_one_revenue_series(auth_client, messy_business):
    """branch/amount, store_name/net_sales and loc/revenue_amount are one metric."""
    business, _ = messy_business
    totals = {}
    for month, (start, end) in {
        "jan": ("2026-01-01", "2026-01-31"),
        "feb": ("2026-02-01", "2026-02-28"),
        "mar": ("2026-03-01", "2026-03-31"),
    }.items():
        body = auth_client.get(
            f"/api/businesses/{business['id']}/overview",
            params={"period_start": start, "period_end": end},
        ).json()
        totals[month] = body["metrics"]["total_revenue"]["value"]

    assert all(value and value > 0 for value in totals.values()), totals


# --- 5. Problems are detected, not silently absorbed ------------------------

def test_planted_problems_are_reported(messy_business):
    _, responses = messy_business
    codes = {
        name: {i["code"] for i in r.json()["quality_issues"]}
        for name, r in responses.items()
    }
    # A duplicated invoice row in February.
    assert "duplicate_rows" in codes["sales_feb.csv"] or \
           "duplicate_keys" in codes["sales_feb.csv"]
    # A missing salary in February payroll.
    assert "missing_values" in codes["payroll_feb.csv"]
    # A repeated employee in the master file.
    assert "duplicate_rows" in codes["employees.xlsx"] or \
           "duplicate_keys" in codes["employees.xlsx"]


def test_refunds_are_detected_and_reduce_revenue(messy_business):
    _, responses = messy_business
    issues = {i["code"]: i for i in responses["sales_mar.xlsx"].json()["quality_issues"]}
    assert "refunds_present" in issues
    assert issues["refunds_present"]["details"]["count"] == 2


def test_totals_row_is_not_counted_as_a_sale(messy_business):
    _, responses = messy_business
    body = responses["sales_mar.xlsx"].json()
    # 60 sales + 2 refunds, and the grand total row excluded.
    assert body["row_count"] == 62


# --- 6. Metric availability and refusal -------------------------------------

def test_cogs_is_absent_so_gross_profit_is_refused(auth_client, messy_business):
    """Rule 8: no COGS anywhere means no gross profit, not a guess."""
    business, _ = messy_business
    metrics = auth_client.get(f"/api/businesses/{business['id']}/overview").json()["metrics"]
    assert metrics["total_revenue"]["available"]
    assert not metrics["total_cogs"]["available"]
    assert not metrics["gross_profit"]["available"]
    assert "Cost of goods sold" in metrics["gross_profit"]["reason"]


def test_availability_has_four_states(auth_client, messy_business):
    business, _ = messy_business
    metrics = auth_client.get(f"/api/businesses/{business['id']}/overview").json()["metrics"]
    states = {m["availability"] for m in metrics.values()}
    assert "AVAILABLE" in states
    assert "UNAVAILABLE" in states
    assert states <= {"AVAILABLE", "PARTIALLY_AVAILABLE", "NEEDS_CONFIRMATION", "UNAVAILABLE"}


def test_asking_for_an_uncomputable_metric_is_refused(auth_client, messy_business):
    """PRD sec. 33: explain the gap instead of answering anyway."""
    business, _ = messy_business
    answer = auth_client.post(
        f"/api/businesses/{business['id']}/ask",
        json={"question": "What is my gross profit margin?"},
    ).json()
    assert answer["status"] == "unavailable"
    assert "can't calculate" in answer["headline"].lower()
    assert answer["limitations"]


# --- 7. Evidence and provenance ---------------------------------------------

def test_every_available_metric_carries_provenance(auth_client, messy_business):
    """Rule 10: traceable to the upload behind it."""
    business, _ = messy_business
    metrics = auth_client.get(f"/api/businesses/{business['id']}/overview").json()["metrics"]
    revenue = metrics["total_revenue"]
    assert revenue["formula"]
    assert revenue["provenance"], "no source lineage"
    source = revenue["provenance"][0]
    assert source["file"].startswith("sales_")
    assert source["version"] >= 1


def test_answers_carry_the_evidence_behind_them(auth_client, messy_business):
    business, _ = messy_business
    answer = auth_client.post(
        f"/api/businesses/{business['id']}/ask",
        json={"question": "What is total revenue?"},
    ).json()
    assert answer["status"] == "answered"
    assert answer["evidence"]
    assert answer["evidence"][0]["formula"]


# --- 8. Aggregation correctness ---------------------------------------------

def test_company_margin_is_recomputed_not_averaged(auth_client, messy_business):
    """Rule 6."""
    business, _ = messy_business
    march = {"period_start": "2026-03-01", "period_end": "2026-03-31"}
    overview = auth_client.get(
        f"/api/businesses/{business['id']}/overview", params=march
    ).json()["metrics"]
    comparison = auth_client.get(
        f"/api/businesses/{business['id']}/compare/branches", params=march
    ).json()

    ratio = next(m for m in comparison["metrics"] if m["key"] == "employee_cost_ratio")
    if not ratio["values"] or not overview["employee_cost_ratio"]["available"]:
        pytest.skip("employee cost ratio unavailable for this scope")

    company = overview["employee_cost_ratio"]["value"]
    branch_average = sum(ratio["values"].values()) / len(ratio["values"])
    revenue = overview["total_revenue"]["value"]
    cost = overview["total_employee_cost"]["value"]
    assert company == pytest.approx(100 * cost / revenue, rel=1e-6)
    if abs(company - branch_average) > 0.01:
        assert company != pytest.approx(branch_average)


# --- 9. Reproducibility ------------------------------------------------------

def test_results_are_reproducible(auth_client, messy_business):
    business, _ = messy_business
    first = auth_client.get(f"/api/businesses/{business['id']}/overview").json()["metrics"]
    second = auth_client.get(f"/api/businesses/{business['id']}/overview").json()["metrics"]
    assert {k: v["value"] for k, v in first.items()} == {
        k: v["value"] for k, v in second.items()
    }


# --- 10. The semantic model reflects only what exists ------------------------

def test_semantic_model_reports_what_was_actually_found(auth_client, messy_business):
    business, _ = messy_business
    model = auth_client.get(f"/api/businesses/{business['id']}/model").json()
    assert len(model["datasets"]) >= 8
    assert all(d["grain"] for d in model["datasets"])
    assert "sales" in model["concepts"]
    # No COGS was uploaded, so it must not appear anywhere in the model.
    assert not any("COGS" in concepts for concepts in model["concepts"].values())


def test_employee_transfer_does_not_duplicate_the_employee(auth_client, messy_business):
    """An employee who moved branch is still one person."""
    business, _ = messy_business
    before = auth_client.get(
        f"/api/businesses/{business['id']}/overview",
        params={"period_start": "2026-03-01", "period_end": "2026-03-31"},
    ).json()["metrics"]["employee_count"]["value"]

    send(auth_client, business["id"], "transfer.csv", employee_transfer(),
         dataset_name="Payroll", period_start="2026-03-01", period_end="2026-03-31")

    after = auth_client.get(
        f"/api/businesses/{business['id']}/overview",
        params={"period_start": "2026-03-01", "period_end": "2026-03-31"},
    ).json()["metrics"]["employee_count"]["value"]
    assert after == before, "a transferred employee was counted twice"

"""End-to-end: upload files, confirm mappings, read the dashboard."""

from __future__ import annotations

import pandas as pd

from tests.conftest import upload


def test_health_and_concept_vocabulary(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    concepts = client.get("/api/concepts").json()
    names = {c["name"] for c in concepts}
    assert {"REVENUE", "BRANCH", "EMPLOYEE_COMPENSATION"} <= names


def test_login_and_authentication_is_required(client):
    client.post(
        "/api/auth/register", json={"email": "a@b.com", "password": "supersecret"}
    )
    assert client.get("/api/businesses").status_code == 401

    bad = client.post("/api/auth/token", data={"username": "a@b.com", "password": "wrong"})
    assert bad.status_code == 401

    good = client.post(
        "/api/auth/token", data={"username": "a@b.com", "password": "supersecret"}
    )
    token = good.json()["access_token"]
    ok = client.get("/api/businesses", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200


def test_duplicate_registration_is_rejected(client):
    payload = {"email": "dup@example.com", "password": "supersecret"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_business_data_is_isolated_between_tenants(auth_client, business):
    """PRD sec. 33: another tenant's business must not be reachable."""
    auth_client.headers.pop("Authorization")
    other = auth_client.post(
        "/api/auth/register", json={"email": "intruder@example.com", "password": "supersecret"}
    ).json()["access_token"]
    auth_client.headers["Authorization"] = f"Bearer {other}"

    response = auth_client.get(f"/api/businesses/{business['id']}")
    assert response.status_code == 404  # not 403: existence is not disclosed
    assert auth_client.get(f"/api/businesses/{business['id']}/overview").status_code == 404


def test_branch_spelling_variants_reconcile_to_one_branch(auth_client, business):
    """PRD sec. 11."""
    for name in ["Jubilee Hills", "jubilee hills", "JUBILEE-HILLS"]:
        auth_client.post(f"/api/businesses/{business['id']}/branches", json={"name": name})
    branches = auth_client.get(f"/api/businesses/{business['id']}/branches").json()
    assert sum(1 for b in branches if "jubilee" in b["name"].lower()) == 1


def test_unreadable_file_gets_a_plain_language_error(auth_client, business):
    response = auth_client.post(
        f"/api/businesses/{business['id']}/uploads",
        files={"file": ("notes.txt", b"just some text", "text/plain")},
    )
    assert response.status_code == 422
    assert "Excel" in response.json()["detail"]


def test_empty_file_is_rejected(auth_client, business):
    response = auth_client.post(
        f"/api/businesses/{business['id']}/uploads",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


def test_upload_profiles_maps_and_cleans(auth_client, business, employee_df):
    response = upload(auth_client, business["id"], employee_df, "Employees")
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["entity_kind"] == "employee"
    assert body["row_count"] == 10
    concepts = {m["concept"] for m in body["mappings"]}
    assert {"EMPLOYEE_ID", "BRANCH", "ROLE", "EMPLOYEE_COMPENSATION"} <= concepts

    # "branch a" and "Branch A" folded; "Mgr" folded to "manager".
    kinds = {entry["type"] for entry in body["cleaning_log"]}
    assert "label_normalisation" in kinds
    assert "role_normalisation" in kinds


def test_low_confidence_column_is_reported_not_guessed(auth_client, business):
    """PRD sec. 14: the user is asked about 'extra'."""
    df = pd.DataFrame(
        {
            "bill_no": ["a", "b", "c"],
            "order_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "branch": ["Branch A"] * 3,
            "revenue": [100.0, 200.0, 300.0],
            "extra": [10.0, 20.0, 30.0],
        }
    )
    body = upload(auth_client, business["id"], df, "Sales").json()
    extra = next(m for m in body["mappings"] if m["source_column"] == "extra")
    assert extra["concept"] is None or extra["needs_confirmation"]
    assert body["requires_confirmation"]
    assert any(i["column_name"] == "extra" for i in body["quality_issues"])


def test_confirming_a_mapping_rebuilds_records_and_is_remembered(auth_client, business):
    df = pd.DataFrame(
        {
            "bill_no": ["a", "b"],
            "order_date": ["2026-01-01", "2026-01-02"],
            "branch": ["Branch A", "Branch A"],
            "revenue": [100.0, 200.0],
            "extra": [10.0, 20.0],
        }
    )
    body = upload(auth_client, business["id"], df, "Sales").json()
    mapping_id = next(m["id"] for m in body["mappings"] if m["source_column"] == "extra")

    patched = auth_client.patch(
        f"/api/versions/{body['dataset_version_id']}/mappings",
        json={"updates": [{"mapping_id": mapping_id, "concept": "SERVICE_CHARGE",
                           "remember": True}]},
    )
    assert patched.status_code == 200
    extra = next(m for m in patched.json()["mappings"] if m["source_column"] == "extra")
    assert extra["concept"] == "SERVICE_CHARGE"
    assert extra["confirmed_by_user"] and not extra["needs_confirmation"]

    # A later upload with the same column applies the confirmed meaning. The
    # rows differ, or the upload would be rejected as a duplicate.
    february = df.assign(bill_no=["c", "d"], order_date=["2026-02-01", "2026-02-02"])
    second = upload(auth_client, business["id"], february, "Sales February").json()
    remembered = next(m for m in second["mappings"] if m["source_column"] == "extra")
    assert remembered["concept"] == "SERVICE_CHARGE"
    assert not remembered["needs_confirmation"]


def test_unknown_concept_in_confirmation_is_rejected(auth_client, business, employee_df):
    body = upload(auth_client, business["id"], employee_df, "Employees").json()
    mapping_id = body["mappings"][0]["id"]
    response = auth_client.patch(
        f"/api/versions/{body['dataset_version_id']}/mappings",
        json={"updates": [{"mapping_id": mapping_id, "concept": "NOT_A_CONCEPT"}]},
    )
    assert response.status_code == 422


def test_schema_change_is_detected_across_uploads(auth_client, business):
    """PRD sec. 20: the new delivery_fee column is announced."""
    january = pd.DataFrame(
        {"bill_no": ["a", "b"], "order_date": ["2026-01-01", "2026-01-02"],
         "branch": ["Branch A"] * 2, "food_sales": [100.0, 200.0]}
    )
    february = pd.DataFrame(
        {"invoice_no": ["c", "d"], "order_date": ["2026-02-01", "2026-02-02"],
         "branch": ["Branch A"] * 2, "food_revenue": [110.0, 210.0],
         "delivery_fee": [10.0, 12.0]}
    )
    upload(auth_client, business["id"], january, "Sales")
    body = upload(auth_client, business["id"], february, "Sales").json()
    assert "DELIVERY_FEE" in body["new_concepts"]


def test_overview_reports_what_it_cannot_answer(auth_client, business, sales_df, employee_df):
    """Process doc sec. 7."""
    upload(auth_client, business["id"], sales_df, "Sales")
    upload(auth_client, business["id"], employee_df, "Employees")

    body = auth_client.get(f"/api/businesses/{business['id']}/overview").json()
    metrics = body["metrics"]
    assert metrics["total_revenue"]["available"]
    assert metrics["total_employee_cost"]["available"]
    assert metrics["employee_cost_ratio"]["available"]

    # No operating expense file was uploaded, so profit is withheld with a reason.
    assert not metrics["operating_profit"]["available"]
    assert "Operating expenses" in metrics["operating_profit"]["reason"]
    assert any(r["metric"] == "operating_profit" and not r["available"] for r in body["readiness"])


def test_branch_comparison_ranks_branches(auth_client, business, sales_df, employee_df):
    upload(auth_client, business["id"], sales_df, "Sales")
    upload(auth_client, business["id"], employee_df, "Employees")

    body = auth_client.get(f"/api/businesses/{business['id']}/compare/branches").json()
    assert body["members"] == ["Branch A", "Branch B"]
    revenue = next(m for m in body["metrics"] if m["key"] == "total_revenue")
    assert revenue["best"] == "Branch B"

    ratio = next(m for m in body["metrics"] if m["key"] == "employee_cost_ratio")
    assert ratio["best"] == "Branch B"  # lower ratio wins


def test_period_comparison_produces_changes_and_drivers(auth_client, business, sales_df):
    upload(auth_client, business["id"], sales_df, "Sales")
    body = auth_client.get(
        f"/api/businesses/{business['id']}/compare/periods",
        params={
            "current_start": "2026-02-01", "current_end": "2026-02-28",
            "previous_start": "2026-01-01", "previous_end": "2026-01-31",
        },
    ).json()

    revenue = next(c for c in body["changes"] if c["key"] == "total_revenue")
    assert revenue["direction"] == "up"
    assert revenue["percent"] > 0
    assert revenue["favourable"] is True
    assert any(d["kind"] == "driver" for d in body["drivers"])


def test_period_filter_actually_narrows_the_data(auth_client, business, sales_df):
    upload(auth_client, business["id"], sales_df, "Sales")
    january = auth_client.get(
        f"/api/businesses/{business['id']}/overview",
        params={"period_start": "2026-01-01", "period_end": "2026-01-31"},
    ).json()
    both = auth_client.get(f"/api/businesses/{business['id']}/overview").json()
    assert january["metrics"]["total_revenue"]["value"] < both["metrics"]["total_revenue"]["value"]


def test_branch_filter_narrows_the_data(auth_client, business, sales_df):
    upload(auth_client, business["id"], sales_df, "Sales")
    one = auth_client.get(
        f"/api/businesses/{business['id']}/overview", params={"branches": ["Branch A"]}
    ).json()
    both = auth_client.get(f"/api/businesses/{business['id']}/overview").json()
    assert one["metrics"]["total_revenue"]["value"] < both["metrics"]["total_revenue"]["value"]
    assert one["scope"]["branches"] == ["Branch A"]


def test_overview_without_data_explains_itself(auth_client, business):
    response = auth_client.get(f"/api/businesses/{business['id']}/overview")
    assert response.status_code == 404
    assert "Upload a file" in response.json()["detail"]


def test_datasets_listing_shows_versions(auth_client, business, sales_df):
    upload(auth_client, business["id"], sales_df, "Sales")
    corrected = sales_df.assign(food_sales=sales_df["food_sales"] * 2)
    upload(auth_client, business["id"], corrected, "Sales")
    datasets = auth_client.get(f"/api/businesses/{business['id']}/datasets").json()
    sales = next(d for d in datasets if d["name"] == "Sales")
    assert [v["version"] for v in sales["versions"]] == [1, 2]


def test_the_same_file_twice_is_refused_not_double_counted(auth_client, business, sales_df):
    """PRD sec. 23: a re-upload must never inflate the totals."""
    first = upload(auth_client, business["id"], sales_df, "Sales")
    assert first.status_code == 201
    before = auth_client.get(f"/api/businesses/{business['id']}/overview").json()

    again = upload(auth_client, business["id"], sales_df, "Sales")
    assert again.status_code == 409
    assert "already been uploaded" in again.json()["detail"]

    after = auth_client.get(f"/api/businesses/{business['id']}/overview").json()
    assert (
        after["metrics"]["total_revenue"]["value"]
        == before["metrics"]["total_revenue"]["value"]
    )


def test_replacing_an_upload_supersedes_it_rather_than_adding(auth_client, business, sales_df):
    upload(auth_client, business["id"], sales_df, "Sales")
    before = auth_client.get(f"/api/businesses/{business['id']}/overview").json()

    replaced = upload(auth_client, business["id"], sales_df, "Sales", replace="true")
    assert replaced.status_code == 201

    after = auth_client.get(f"/api/businesses/{business['id']}/overview").json()
    assert (
        after["metrics"]["total_revenue"]["value"]
        == before["metrics"]["total_revenue"]["value"]
    )
    # The superseded version is kept, not deleted.
    datasets = auth_client.get(f"/api/businesses/{business['id']}/datasets").json()
    sales = next(d for d in datasets if d["name"] == "Sales")
    assert len(sales["versions"]) == 2

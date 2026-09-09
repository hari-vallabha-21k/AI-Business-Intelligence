"""Test fixtures: an isolated database and an authenticated client per test."""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("BI_SECRET_KEY", "test-secret")


@pytest.fixture
def db_session():
    import app.models  # noqa: F401 - registers the tables on Base.metadata
    from app.db import Base

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_client(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "owner@example.com", "password": "supersecret", "full_name": "Owner"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def business(auth_client):
    response = auth_client.post(
        "/api/businesses",
        json={"name": "Spice Route", "currency": "INR", "branches": ["Branch A", "Branch B"]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode()


def upload(client, business_id: int, df: pd.DataFrame, name: str, **form) -> dict:
    response = client.post(
        f"/api/businesses/{business_id}/uploads",
        files={"file": (f"{name}.csv", to_csv_bytes(df), "text/csv")},
        data={"dataset_name": name, **{k: str(v) for k, v in form.items() if v is not None}},
    )
    return response


@pytest.fixture
def sales_df():
    """Two branches, two months, with an obvious profit story."""
    rows = []
    for month, (rev_a, rev_b) in {"01": (30000, 35000), "02": (33000, 40000)}.items():
        for day in range(1, 11):
            rows.append(
                {
                    "bill_no": f"A{month}{day}",
                    "order_date": f"2026-{month}-{day:02d}",
                    "location": "Branch A",
                    "item": "Chicken Biryani",
                    "food_sales": rev_a,
                    "discount": rev_a * 0.05,
                    "food_cost": rev_a * 0.35,
                }
            )
            rows.append(
                {
                    "bill_no": f"B{month}{day}",
                    "order_date": f"2026-{month}-{day:02d}",
                    "location": "Branch B",
                    "item": "Paneer Tikka",
                    "food_sales": rev_b,
                    "discount": rev_b * 0.04,
                    "food_cost": rev_b * 0.30,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def employee_df():
    rows = []
    for i in range(6):
        rows.append(
            {
                "emp_id": f"A{i}",
                "name": f"Employee A{i}",
                "location": "Branch A" if i % 2 else "branch a",
                "designation": "Mgr" if i == 0 else "waiter",
                "monthly_pay": 40000,
            }
        )
    for i in range(4):
        rows.append(
            {
                "emp_id": f"B{i}",
                "name": f"Employee B{i}",
                "location": "Branch B",
                "designation": "manager" if i == 0 else "Waiter",
                "monthly_pay": 38000,
            }
        )
    return pd.DataFrame(rows)

"""
Unit and integration tests for AcmeOps ERP mock application.
"""

import pytest
from fastapi.testclient import TestClient
from acme_ops.app import app
from acme_ops.database import init_db, set_flag


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db(force_reset=True)
    set_flag("flaky_ui_submit", "0")
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_login_and_session(client):
    # Invalid login
    res = client.post("/login", data={"username": "admin", "password": "wrongpassword"})
    assert res.status_code == 200
    assert "Invalid username" in res.text

    # Valid login
    res = client.post("/login", data={"username": "admin", "password": "acmepass123"}, follow_redirects=False)
    assert res.status_code in (302, 303)
    assert "acme_session" in res.cookies


def test_inbox_requires_auth(client):
    res = client.get("/invoices", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["location"]


def test_create_invoice_web_form(client):
    # Authenticate
    client.post("/login", data={"username": "admin", "password": "acmepass123"})

    payload = {
        "vendor": "Apex Technologies",
        "invoice_number": "INV-TEST-001",
        "amount": "1500.00",
        "currency": "USD",
        "due_date": "2026-12-01",
        "description": "Test Services"
    }
    res = client.post("/invoices/new", data=payload, follow_redirects=False)
    assert res.status_code == 303
    assert "/invoices/" in res.headers["location"]


def test_deliberate_failure_mode_500(client):
    client.post("/login", data={"username": "admin", "password": "acmepass123"})

    # Deliberate failure triggered by vendor "Quantum Logistics"
    payload = {
        "vendor": "Quantum Logistics",
        "invoice_number": "INV-FAIL-500",
        "amount": "2000.00",
        "currency": "USD",
        "due_date": "2026-12-01",
        "description": "Trigger failure"
    }
    res = client.post("/invoices/new", data=payload)
    assert res.status_code == 500
    assert "Database lock timeout" in res.text


def test_duplicate_rejection(client):
    client.post("/login", data={"username": "admin", "password": "acmepass123"})

    payload = {
        "vendor": "Apex Technologies",
        "invoice_number": "INV-DUP-1",
        "amount": "500.00",
        "currency": "USD",
        "due_date": "2026-11-15",
    }
    res1 = client.post("/invoices/new", data=payload, follow_redirects=False)
    assert res1.status_code == 303

    # Duplicate attempt
    res2 = client.post("/invoices/new", data=payload)
    assert res2.status_code == 400
    assert "Duplicate invoice" in res2.text


def test_rest_api_create_and_verify(client):
    # Login via API
    token_res = client.post("/api/auth/token", json={"username": "admin", "password": "acmepass123"})
    assert token_res.status_code == 200
    token = token_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create invoice via REST API
    create_res = client.post("/api/invoices", json={
        "vendor": "API Vendor Corp",
        "invoice_number": "INV-API-99",
        "amount": 2500.50,
        "due_date": "2026-12-15",
        "currency": "USD",
        "description": "API Test"
    }, headers=headers)
    assert create_res.status_code == 201
    assert create_res.json()["source_channel"] == "REST_API"

    # Verify invoice via API
    verify_res = client.get("/api/verify", params={
        "vendor": "API Vendor Corp",
        "invoice_number": "INV-API-99",
        "expected_amount": 2500.50,
        "expected_due_date": "2026-12-15"
    }, headers=headers)
    assert verify_res.status_code == 200
    assert verify_res.json()["matched"] is True

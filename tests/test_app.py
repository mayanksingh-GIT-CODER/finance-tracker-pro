from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.database import Database
from app.main import amount_to_cents, create_app
from app.security import hash_password, verify_password


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "test.db", secret_key="test-secret-key")
    with TestClient(app) as test_client:
        yield test_client


def register(client, name="Mayank Singh", email="mayank@example.com", password="strongpass123"):
    return client.post(
        "/register",
        data={"name": name, "email": email, "password": password},
        follow_redirects=False,
    )


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("strongpass123")
    second = hash_password("strongpass123")
    assert first != second
    assert verify_password("strongpass123", first)
    assert not verify_password("wrong-password", first)


def test_amount_conversion_uses_decimal_rounding():
    assert amount_to_cents("1200.125") == 120013
    with pytest.raises(ValueError):
        amount_to_cents("0")


def test_registration_creates_session_and_dashboard(client):
    response = register(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Welcome, Mayank" in dashboard.text


def test_transaction_appears_in_dashboard_report_and_csv(client):
    register(client)
    response = client.post(
        "/transactions",
        data={
            "kind": "expense",
            "category": "Learning",
            "amount": "1499.50",
            "occurred_on": "2026-07-15",
            "note": "Course subscription",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Learning" in client.get("/dashboard").text
    assert "Course subscription" in client.get("/reports?month=2026-07").text
    exported = client.get("/export.csv?month=2026-07")
    assert exported.status_code == 200
    assert "Learning,1499.50,Course subscription" in exported.text


def test_user_cannot_delete_another_users_transaction(tmp_path):
    database = Database(tmp_path / "isolation.db")
    database.initialize()
    password_hash = hash_password("strongpass123")
    owner = database.create_user("Owner", "owner@example.com", password_hash)
    other = database.create_user("Other", "other@example.com", password_hash)
    transaction_id = database.add_transaction(owner, "income", "Salary", 50_000, date(2026, 7, 1))
    assert database.delete_transaction(other, transaction_id) is False
    assert len(database.transactions(owner)) == 1


def test_health_endpoint_is_public(client):
    response = client.get("/health")
    assert response.json() == {"status": "ok", "service": "finance-tracker-pro"}

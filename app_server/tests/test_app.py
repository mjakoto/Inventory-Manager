from pathlib import Path

import pytest

from app_server.app import create_app


@pytest.fixture()
def client(tmp_path: Path):
    database_path = tmp_path / "test-inventory.db"
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": str(database_path),
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD": "password123",
            "WRITE_RATE_LIMIT": 100,
            "WRITE_RATE_WINDOW_SECONDS": 60,
        }
    )

    with app.test_client() as test_client:
        yield test_client


def login(client):
    response = client.post(
        "/login",
        json={"username": "admin", "password": "password123"},
    )
    assert response.status_code == 200


def create_sample_item(client, **overrides):
    payload = {
        "name": "Router",
        "sku": "RTR-001",
        "quantity": 2,
        "location": "Warehouse A",
        "category": "Networking",
        "low_stock_threshold": 3,
    }
    payload.update(overrides)
    return client.post("/items", json=payload)


def test_requires_auth_for_mutating_routes(client):
    response = create_sample_item(client)
    assert response.status_code == 401


def test_create_update_delete_and_history_flow(client):
    login(client)

    create_response = create_sample_item(client)
    assert create_response.status_code == 201
    item_id = create_response.get_json()["item"]["id"]

    update_response = client.put(
        f"/items/{item_id}",
        json={
            "name": "Router",
            "sku": "RTR-001",
            "quantity": 1,
            "location": "Retail Floor",
            "category": "Networking",
            "low_stock_threshold": 3,
        },
    )
    assert update_response.status_code == 200
    assert update_response.get_json()["item"]["is_low_stock"] is True

    history_response = client.get("/history?limit=10")
    assert history_response.status_code == 200
    history_payload = history_response.get_json()["history"]
    assert history_payload[0]["action"] == "UPDATED"
    assert history_payload[1]["action"] == "CREATED"

    delete_response = client.delete(f"/items/{item_id}")
    assert delete_response.status_code == 200


def test_validation_rejects_invalid_payloads(client):
    login(client)

    response = client.post(
        "/items",
        json={
            "name": "",
            "sku": "BAD-001",
            "quantity": -4,
            "location": "",
            "category": "Hardware",
            "low_stock_threshold": -1,
        },
    )
    assert response.status_code == 400
    assert "name" in response.get_json()["message"] or "quantity" in response.get_json()["message"]


def test_search_filter_and_low_stock_dashboard(client):
    login(client)
    create_sample_item(client)
    create_sample_item(
        client,
        name="Keyboard",
        sku="KEY-002",
        quantity=14,
        category="Peripherals",
        location="Warehouse B",
        low_stock_threshold=2,
    )

    search_response = client.get("/items?search=key")
    assert search_response.status_code == 200
    search_items = search_response.get_json()["items"]
    assert len(search_items) == 1
    assert search_items[0]["name"] == "Keyboard"

    low_stock_response = client.get("/items?stock_status=low_stock")
    assert low_stock_response.status_code == 200
    low_stock_items = low_stock_response.get_json()["items"]
    assert len(low_stock_items) == 1
    assert low_stock_items[0]["sku"] == "RTR-001"

    dashboard_response = client.get("/dashboard")
    assert dashboard_response.status_code == 200
    assert dashboard_response.get_json()["summary"]["low_stock_count"] == 1


def test_health_ready_and_metrics_endpoints(client):
    health_response = client.get("/healthz")
    ready_response = client.get("/readyz")
    metrics_response = client.get("/metrics")

    assert health_response.status_code == 200
    assert ready_response.status_code == 200
    assert metrics_response.status_code == 200
    assert "inventory_http_requests_total" in metrics_response.get_data(as_text=True)

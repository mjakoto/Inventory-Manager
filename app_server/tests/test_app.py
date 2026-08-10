import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_server.app import create_app  # noqa: E402


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
        "vendor": "Cisco",
        "description": "Core branch router",
        "serial_number": "SN-100",
        "unit_cost": 499.99,
        "reorder_point": 3,
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
            "vendor": "Cisco",
            "description": "Core branch router",
            "serial_number": "SN-100",
            "unit_cost": 499.99,
            "reorder_point": 3,
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
            "vendor": "Dell",
            "description": "",
            "serial_number": "",
            "unit_cost": -1,
            "reorder_point": -1,
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
        vendor="Dell",
        description="Hot desk keyboard",
        serial_number="SN-200",
        unit_cost=59.99,
        reorder_point=2,
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


def test_stock_actions_and_vendor_filter(client):
    login(client)
    create_response = create_sample_item(client)
    item = create_response.get_json()["item"]

    add_response = client.post(
        f"/items/{item['id']}/stock-actions",
        json={"action": "add", "quantity": 5, "note": "Received delivery"},
    )
    assert add_response.status_code == 200
    assert add_response.get_json()["item"]["quantity"] == 7

    remove_response = client.post(
        f"/items/{item['id']}/stock-actions",
        json={"action": "remove", "quantity": 2},
    )
    assert remove_response.status_code == 200
    assert remove_response.get_json()["item"]["quantity"] == 5

    adjust_response = client.post(
        f"/items/{item['id']}/stock-actions",
        json={"action": "adjust", "quantity": 11},
    )
    assert adjust_response.status_code == 200
    adjusted_item = adjust_response.get_json()["item"]
    assert adjusted_item["quantity"] == 11

    transfer_response = client.post(
        f"/items/{item['id']}/stock-actions",
        json={"action": "transfer", "destination_location": "Data Center Cage"},
    )
    assert transfer_response.status_code == 200
    transferred_item = transfer_response.get_json()["item"]
    assert transferred_item["location"] == "Data Center Cage"

    vendor_response = client.get("/items?vendor=Cisco")
    assert vendor_response.status_code == 200
    vendor_items = vendor_response.get_json()["items"]
    assert len(vendor_items) == 1
    assert vendor_items[0]["vendor"] == "Cisco"


def test_health_ready_and_metrics_endpoints(client):
    health_response = client.get("/healthz")
    ready_response = client.get("/readyz")
    metrics_response = client.get("/metrics")

    assert health_response.status_code == 200
    assert ready_response.status_code == 200
    assert metrics_response.status_code == 200
    assert "inventory_http_requests_total" in metrics_response.get_data(as_text=True)

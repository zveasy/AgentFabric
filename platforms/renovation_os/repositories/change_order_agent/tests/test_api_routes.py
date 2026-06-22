from fastapi.testclient import TestClient
from change_order_agent.api import app


def test_create_change_order_route() -> None:
    response = TestClient(app).post("/change-orders", json={
        "change_order_id": "co1", "description": "Move wall", "cost_delta": 1500, "schedule_days": 2
    })
    assert response.status_code == 200
    assert response.json()["status"] == "draft"

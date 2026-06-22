from fastapi.testclient import TestClient
from reno_estimator.api import app


def test_estimate_route() -> None:
    response = TestClient(app).post("/estimates", json={
        "project_id": "p1",
        "location": "local",
        "rooms": [{"name": "Kitchen", "area_sqft": 100, "material_category": "standard", "labor_hours": 10}],
        "labor": {"hourly_rate": 50, "location_adjustment": 1.0},
    })
    assert response.status_code == 200
    assert set(response.json()["scenarios"]) == {"low", "base", "high"}

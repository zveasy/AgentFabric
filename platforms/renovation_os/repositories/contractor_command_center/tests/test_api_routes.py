from fastapi.testclient import TestClient
from contractor_command_center.api import app


def test_reliability_route() -> None:
    response = TestClient(app).post(
        "/contractors/reliability", json={"contractor_id": "c1", "name": "Reliable Co"}
    )
    assert response.status_code == 200
    assert response.json()["reliability_score"] == 50.0

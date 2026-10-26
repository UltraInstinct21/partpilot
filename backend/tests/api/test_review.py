"""The review queue: ``GET /api/review`` and ``POST /api/review/{param_id}``."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_review_queue_lists_low_confidence_values(client: TestClient) -> None:
    response = client.get("/api/review")
    assert response.status_code == 200
    payload = response.json()
    assert payload, "the seeded parts must have something to review"
    item = payload[0]
    assert set(item) >= {
        "param_id",
        "part_id",
        "mpn",
        "manufacturer",
        "family",
        "name",
        "confidence",
        "status",
        "reasons",
    }
    assert item["status"] == "review"
    assert item["confidence"] < 0.75


def test_review_queue_honours_the_limit(client: TestClient) -> None:
    payload = client.get("/api/review", params={"limit": 2}).json()
    assert len(payload) == 2


def test_review_queue_rejects_a_limit_out_of_range(client: TestClient) -> None:
    assert client.get("/api/review", params={"limit": 0}).status_code == 422


def test_review_accepts_a_value(client: TestClient) -> None:
    item = client.get("/api/review").json()[0]
    response = client.post(f"/api/review/{item['param_id']}", json={"action": "accept"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["param_id"] == item["param_id"]
    assert payload["status"] == "accepted"
    assert payload["message"]


def test_review_corrects_a_value(client: TestClient) -> None:
    item = client.get("/api/review").json()[0]
    response = client.post(
        f"/api/review/{item['param_id']}",
        json={"action": "correct", "value": 3.3, "unit": "V", "note": "checked by hand"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_review_rejects_a_value(client: TestClient) -> None:
    item = client.get("/api/review").json()[0]
    response = client.post(f"/api/review/{item['param_id']}", json={"action": "reject"})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_review_rejects_an_unknown_action(client: TestClient) -> None:
    item = client.get("/api/review").json()[0]
    response = client.post(f"/api/review/{item['param_id']}", json={"action": "banana"})
    assert response.status_code == 422


def test_review_of_an_unknown_value_is_a_404(client: TestClient) -> None:
    response = client.post("/api/review/nope", json={"action": "accept"})
    assert response.status_code == 404


def test_review_advisory_generates_recommendations_and_tradeoffs(client: TestClient) -> None:
    response = client.post(
        "/api/review/advisory",
        json={
            "parts": [
                {
                    "mpn": "IRF3205S",
                    "manufacturer": "Infineon",
                    "family": "mosfet",
                    "package": "D2PAK",
                    "lifecycle_status": "active",
                    "parameters": {"rds_on": 8.0, "vds": 55.0, "id": 110.0, "qg": 146.0},
                    "stock": 4500,
                    "price": 1.45,
                },
                {
                    "mpn": "IRF540N",
                    "manufacturer": "Vishay",
                    "family": "mosfet",
                    "package": "TO-220",
                    "lifecycle_status": "active",
                    "parameters": {"rds_on": 44.0, "vds": 100.0, "id": 33.0, "qg": 71.0},
                    "stock": 8200,
                    "price": 0.85,
                },
            ],
            "priority": "efficiency",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "executive_summary" in data
    assert "overall_recommendation" in data
    assert len(data["candidate_evaluations"]) == 2
    assert len(data["tradeoffs"]) >= 2
    assert len(data["engineering_suggestions"]) > 0
    assert data["bom_readiness_score"] > 50


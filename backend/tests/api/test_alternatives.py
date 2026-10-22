"""The alternatives endpoint ``GET /api/parts/{id}/alternatives``."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_alternatives_are_ranked(client: TestClient) -> None:
    response = client.get("/api/parts/mosfet-irf3205s/alternatives")
    assert response.status_code == 200
    payload = response.json()
    assert payload, "there must be alternatives for a seeded part"
    first = payload[0]
    assert set(first) >= {"part", "score", "rank", "reason", "rejected"}
    assert first["rank"] == 1
    assert first["part"]["part_id"] != "mosfet-irf3205s"


def test_alternatives_honour_the_limit(client: TestClient) -> None:
    response = client.get("/api/parts/mosfet-irf3205s/alternatives", params={"limit": 2})
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_alternatives_carry_a_reason(client: TestClient) -> None:
    payload = client.get("/api/parts/mosfet-irf3205s/alternatives").json()
    for alternative in payload:
        assert alternative["reason"], "every alternative needs a reason"


def test_alternatives_of_an_unknown_part_is_a_404(client: TestClient) -> None:
    assert client.get("/api/parts/nope/alternatives").status_code == 404


def test_alternatives_reject_a_limit_out_of_range(client: TestClient) -> None:
    response = client.get("/api/parts/mosfet-irf3205s/alternatives", params={"limit": 0})
    assert response.status_code == 422

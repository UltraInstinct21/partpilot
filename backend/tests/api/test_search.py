"""The natural-language search endpoint ``POST /api/search``."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_search_returns_a_filter_and_results(client: TestClient) -> None:
    response = client.post("/api/search", json={"query": "100 V N-channel MOSFET"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "100 V N-channel MOSFET"
    assert "filter" in payload
    assert payload["total"] >= 0
    assert payload["llm_used"] is True
    assert "took_ms" in payload


def test_search_executes_the_filter_that_the_llm_built(client: TestClient) -> None:
    payload = client.post(
        "/api/search", json={"query": "100 V N-channel MOSFET, Rds(on) below 5 mohm"}
    ).json()
    constraints = {c["name"]: c for c in payload["filter"].get("parameters", [])}
    assert "rds_on" in constraints
    # The rows are chosen by the database, never by the model.
    for part in payload["results"]:
        assert part["family"] == "mosfet"


def test_search_with_an_explicit_filter_does_not_call_the_llm(client: TestClient) -> None:
    response = client.post(
        "/api/search",
        json={
            "query": "anything",
            "filter": {"family": "gate_driver"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["llm_used"] is False
    assert {part["family"] for part in payload["results"]} == {"gate_driver"}


def test_search_honours_limit_and_offset(client: TestClient) -> None:
    first = client.post("/api/search", json={"query": "MOSFET", "limit": 3}).json()
    second = client.post("/api/search", json={"query": "MOSFET", "limit": 3, "offset": 3}).json()
    assert len(first["results"]) == 3
    assert len(second["results"]) == 3
    first_ids = {part["part_id"] for part in first["results"]}
    second_ids = {part["part_id"] for part in second["results"]}
    assert not (first_ids & second_ids)


def test_search_needs_a_query(client: TestClient) -> None:
    assert client.post("/api/search", json={}).status_code == 422
    assert client.post("/api/search", json={"query": ""}).status_code == 422


def test_search_rejects_a_limit_out_of_range(client: TestClient) -> None:
    response = client.post("/api/search", json={"query": "MOSFET", "limit": 0})
    assert response.status_code == 422


def test_search_is_rate_limited(client_factory) -> None:
    with client_factory(limit=2) as client:
        assert client.post("/api/search", json={"query": "MOSFET"}).status_code == 200
        assert client.post("/api/search", json={"query": "MOSFET"}).status_code == 200
        response = client.post("/api/search", json={"query": "MOSFET"})
        assert response.status_code == 429
        assert "detail" in response.json()
        assert response.headers.get("Retry-After")


def test_the_rate_limit_does_not_block_the_other_endpoints(client_factory) -> None:
    with client_factory(limit=1) as client:
        client.post("/api/search", json={"query": "MOSFET"})
        client.post("/api/search", json={"query": "MOSFET"})
        assert client.get("/api/parts").status_code == 200
        assert client.get("/api/stats").status_code == 200

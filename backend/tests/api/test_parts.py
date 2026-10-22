"""The catalogue endpoints: ``/api/parts`` and ``/api/parts/{id}``."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_parts_returns_the_seed(client: TestClient) -> None:
    response = client.get("/api/parts")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 30
    assert len(payload["results"]) == 30
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    first = payload["results"][0]
    assert set(first) >= {
        "part_id",
        "mpn",
        "manufacturer",
        "family",
        "lifecycle_status",
        "key_parameters",
    }


def test_list_parts_filters_by_family(client: TestClient) -> None:
    response = client.get("/api/parts", params={"family": "mosfet"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 15
    assert {part["family"] for part in payload["results"]} == {"mosfet"}


def test_list_parts_filters_by_manufacturer(client: TestClient) -> None:
    response = client.get("/api/parts", params={"manufacturer": "onsemi"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert {part["manufacturer"] for part in payload["results"]} == {"onsemi"}


def test_list_parts_filters_by_lifecycle_status(client: TestClient) -> None:
    response = client.get("/api/parts", params={"lifecycle_status": "nrnd"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["results"][0]["mpn"] == "AOD4184A"


def test_list_parts_rejects_an_unknown_lifecycle_status(client: TestClient) -> None:
    response = client.get("/api/parts", params={"lifecycle_status": "banana"})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_list_parts_paginates(client: TestClient) -> None:
    first = client.get("/api/parts", params={"limit": 5, "offset": 0}).json()
    second = client.get("/api/parts", params={"limit": 5, "offset": 5}).json()
    assert len(first["results"]) == 5
    assert len(second["results"]) == 5
    assert first["total"] == second["total"] == 30
    first_ids = {part["part_id"] for part in first["results"]}
    second_ids = {part["part_id"] for part in second["results"]}
    assert not (first_ids & second_ids)


def test_list_parts_rejects_a_limit_out_of_range(client: TestClient) -> None:
    assert client.get("/api/parts", params={"limit": 0}).status_code == 422
    assert client.get("/api/parts", params={"limit": 5000}).status_code == 422
    assert client.get("/api/parts", params={"offset": -1}).status_code == 422


def test_get_part_returns_the_part_with_its_values(client: TestClient) -> None:
    response = client.get("/api/parts/mosfet-irf3205s")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mpn"] == "IRF3205S"
    assert payload["family"] == "mosfet"
    assert payload["lifecycle_status"] == "active"
    assert payload["parameters"], "a part must carry its values"
    parameter = payload["parameters"][0]
    assert set(parameter) >= {
        "param_id",
        "name",
        "value",
        "unit",
        "condition",
        "source_id",
        "page",
        "method",
        "confidence",
        "status",
    }


def test_get_part_every_value_carries_its_provenance(client: TestClient) -> None:
    payload = client.get("/api/parts/mosfet-irf3205s").json()
    for parameter in payload["parameters"]:
        assert parameter["source_id"], "every value needs a source"
        assert parameter["page"] is not None
        assert parameter["method"] in {"tier1", "tier2", "tier3", "api", "manual"}
        assert 0.0 <= parameter["confidence"] <= 1.0
        assert parameter["status"] in {"accepted", "review", "rejected"}


def test_get_unknown_part_is_a_404(client: TestClient) -> None:
    response = client.get("/api/parts/does-not-exist")
    assert response.status_code == 404
    assert "detail" in response.json()

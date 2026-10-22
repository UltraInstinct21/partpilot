"""The provenance endpoints: the source of a value and the datasheet page."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _first_param_id(client: TestClient, part_id: str) -> str:
    payload = client.get(f"/api/parts/{part_id}").json()
    return payload["parameters"][0]["param_id"]


def test_parameter_source_returns_the_value_and_its_source(client: TestClient) -> None:
    part_id = "mosfet-irf3205s"
    param_id = _first_param_id(client, part_id)
    response = client.get(f"/api/parts/{part_id}/sources/{param_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["value"]["param_id"] == param_id
    assert payload["source"]["source_id"]
    assert payload["source"]["url"]
    assert payload["source"]["type"] in {"api", "pdf", "manual"}


def test_parameter_source_of_an_unknown_part_is_a_404(client: TestClient) -> None:
    response = client.get("/api/parts/nope/sources/nope")
    assert response.status_code == 404


def test_parameter_source_of_an_unknown_value_is_a_404(client: TestClient) -> None:
    response = client.get("/api/parts/mosfet-irf3205s/sources/nope")
    assert response.status_code == 404


def test_source_page_returns_the_metadata_and_the_text(client: TestClient) -> None:
    response = client.get("/api/sources/pdf-mosfet-irf3205s/page/2")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_id"] == "pdf-mosfet-irf3205s"
    assert payload["page"] == 2
    assert payload["width"] and payload["height"]
    assert "Electrical Characteristics" in payload["text"]
    assert payload["image_url"].endswith("format=image")


def test_source_page_can_return_the_rendered_image(client: TestClient) -> None:
    response = client.get("/api/sources/pdf-mosfet-irf3205s/page/2", params={"format": "image"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")


def test_source_page_rejects_a_page_below_one(client: TestClient) -> None:
    assert client.get("/api/sources/pdf-mosfet-irf3205s/page/0").status_code == 422


def test_source_page_of_an_unknown_source_is_a_404(client: TestClient) -> None:
    assert client.get("/api/sources/nope/page/1").status_code == 404


def test_an_api_source_has_no_page_to_render(client: TestClient) -> None:
    # An API source has no local PDF, so there is no page to show.
    response = client.get("/api/sources/api-digikey-irf3205s/page/1")
    assert response.status_code == 404

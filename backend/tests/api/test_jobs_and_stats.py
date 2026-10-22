"""The background job endpoints and the statistics endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_starting_an_extraction_job_is_accepted(client: TestClient) -> None:
    response = client.post("/api/jobs/extract", json={"part_id": "mosfet-irf3205s"})
    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"]
    assert payload["state"] in {"queued", "running", "completed", "failed"}
    assert payload["part_id"] == "mosfet-irf3205s"


def test_a_job_can_be_polled(client: TestClient) -> None:
    job_id = client.post("/api/jobs/extract", json={"part_id": "mosfet-irf3205s"}).json()["job_id"]
    response = client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["job_id"] == job_id


def test_an_unknown_job_is_a_404(client: TestClient) -> None:
    assert client.get("/api/jobs/nope").status_code == 404


def test_stats_reports_the_seed(client: TestClient) -> None:
    response = client.get("/api/stats")
    assert response.status_code == 200
    payload = response.json()
    assert payload["parts_total"] == 30
    assert payload["parts_by_family"]["mosfet"] == 15
    assert payload["parts_by_family"]["gate_driver"] == 15
    assert payload["parameters_total"] > 0
    assert payload["values_by_status"]
    assert "generated_at" in payload


def test_the_health_probe_is_available(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

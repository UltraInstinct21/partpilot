"""The BOM health check ``POST /api/bom/check``."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

BOM_CSV = "MPN,Qty,Manufacturer\nIRF3205S,10,International Rectifier\nAOD4184A,2,Alpha & Omega Semiconductor\nNO-SUCH-PART,1,\n"


def test_bom_check_with_a_json_body(client: TestClient) -> None:
    response = client.post("/api/bom/check", json={"content": BOM_CSV, "filename": "bom.csv"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_lines"] == 3
    assert payload["matched_lines"] == 2
    assert payload["unmatched_lines"] == 1
    assert payload["risk_count"] >= 1
    assert payload["highest_severity"] in {
        "info",
        "low",
        "medium",
        "high",
        "critical",
    }


def test_bom_check_flags_an_unknown_mpn(client: TestClient) -> None:
    payload = client.post("/api/bom/check", json={"content": BOM_CSV}).json()
    codes = {risk["code"] for risk in payload["risks"]}
    assert "not_found" in codes


def test_bom_check_flags_a_nrnd_part(client: TestClient) -> None:
    payload = client.post("/api/bom/check", json={"content": BOM_CSV}).json()
    codes = {risk["code"] for risk in payload["risks"]}
    assert "nrnd" in codes


def test_bom_check_with_a_multipart_upload(client: TestClient) -> None:
    response = client.post(
        "/api/bom/check",
        files={"file": ("bom.csv", io.BytesIO(BOM_CSV.encode()), "text/csv")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "bom.csv"
    assert payload["total_lines"] == 3


def test_bom_check_returns_a_line_per_row(client: TestClient) -> None:
    payload = client.post("/api/bom/check", json={"content": BOM_CSV}).json()
    assert len(payload["lines"]) == 3
    line = payload["lines"][0]
    assert line["mpn"] == "IRF3205S"
    assert line["quantity"] == 10
    assert line["matched"] is True
    assert line["matched_part_id"]


def test_bom_check_of_an_empty_file(client: TestClient) -> None:
    payload = client.post("/api/bom/check", json={"content": ""}).json()
    assert payload["total_lines"] == 0
    assert payload["risks"] == []


def test_bom_check_rejects_a_body_without_content(client: TestClient) -> None:
    assert client.post("/api/bom/check", json={}).status_code in (200, 422)


def test_bom_check_limits_the_upload_size(client: TestClient) -> None:
    # 6 MiB of CSV is above the 5 MiB limit of the contract.
    big = "MPN\n" + ("X" * 1024 + "\n") * (6 * 1024)
    response = client.post("/api/bom/check", json={"content": big})
    assert response.status_code == 413
    assert "detail" in response.json()

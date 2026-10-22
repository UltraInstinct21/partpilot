"""Standalone mock API for PartPilot.

Serves the frozen OpenAPI contract with fixture data, so the frontend can be
developed before the real backend exists (and without ever calling a
distributor or an LLM).

    make mock-api        # http://127.0.0.1:8001

The same fixture files drive the browser mock (frontend/src/mocks).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "contracts" / "fixtures"
OPENAPI = REPO_ROOT / "contracts" / "openapi.yaml"

app = FastAPI(
    title="PartPilot Mock API",
    version="1.0.0",
    description="Fixture backed mock of the PartPilot API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


SEED_PARTS: list[dict] = _load(FIXTURES / "seed" / "parts.json")["parts"]
EXPECTED_VALUES: dict = _load(FIXTURES / "pdfs" / "expected_values.json")
PAGE_SAMPLES: list[dict] = [_load(p) for p in sorted((FIXTURES / "pages").glob("page_*.json"))]
GOLD_ROWS: list[dict] = []

_now = datetime.now(UTC)


def _source_id(part: dict) -> str:
    return f"api-digikey-{part['mpn'].lower()}"


def _summary(part: dict, score: float | None = None) -> dict:
    params = part.get("parameters", {})
    keys = {
        "mosfet": ["vds_max", "id_continuous", "rds_on", "total_gate_charge_qg"],
        "gate_driver": [
            "supply_voltage_min",
            "supply_voltage_max",
            "peak_source_current",
            "propagation_delay",
        ],
    }[part["family"]]
    key_parameters = {k: params.get(k, {}).get("value") for k in keys}
    return {
        "part_id": part["part_id"],
        "mpn": part["mpn"],
        "manufacturer": part["manufacturer"],
        "family": part["family"],
        "package": part.get("package"),
        "lifecycle_status": part.get("lifecycle_status", "unknown"),
        "datasheet_url": part.get("datasheet_url"),
        "description": part.get("description"),
        "key_parameters": key_parameters,
        "offers_count": 2,
        "total_stock": 48213,
        "score": score,
    }


def _parameter_values(part: dict) -> list[dict]:
    """Turn the seed parameters into ParameterValue rows with provenance."""
    rows: list[dict] = []
    source_id = _source_id(part)
    for name, spec in part.get("parameters", {}).items():
        value = spec.get("value")
        unit = spec.get("unit")
        rows.append(
            {
                "param_id": f"param-{part['mpn'].lower()}-{name}",
                "part_id": part["part_id"],
                "name": name,
                "value": value,
                "value_min": None,
                "value_typ": value,
                "value_max": None,
                "unit": unit,
                "condition": spec.get("condition", {}),
                "source_id": source_id,
                "page": 1,
                "method": "tier1",
                "confidence": 0.92 if value is not None else 0.6,
                "status": "accepted" if value is not None else "review",
                "raw_text": f"{name} = {value} {unit or ''}".strip(),
                "value_text": f"{value} {unit or ''}".strip(),
            }
        )
    return rows


def _match_filter(filt: dict) -> list[dict]:
    parts = SEED_PARTS
    if filt.get("family"):
        parts = [p for p in parts if p["family"] == filt["family"]]
    if filt.get("manufacturer"):
        parts = [p for p in parts if p["manufacturer"] == filt["manufacturer"]]
    if filt.get("mpn_contains"):
        needle = filt["mpn_contains"].lower()
        parts = [p for p in parts if needle in p["mpn"].lower()]
    if filt.get("package"):
        parts = [p for p in parts if p["package"] == filt["package"]]
    lifecycle = filt.get("lifecycle_status") or []
    if lifecycle:
        parts = [p for p in parts if p["lifecycle_status"] in lifecycle]
    text = (filt.get("text") or "").lower()
    if text:
        parts = [
            p
            for p in parts
            if text in p["mpn"].lower()
            or text in p["manufacturer"].lower()
            or text in (p.get("description") or "").lower()
        ]
    for constraint in filt.get("parameters", []) or []:
        name = constraint.get("name")
        lower, upper = _constraint_bounds(constraint)
        kept = []
        for p in parts:
            spec = p.get("parameters", {}).get(name)
            if not spec or spec.get("value") is None:
                continue
            value = float(spec["value"])
            if lower is not None and value < lower:
                continue
            if upper is not None and value > upper:
                continue
            kept.append(p)
        parts = kept
    return parts


def _constraint_bounds(constraint: dict) -> tuple[float | None, float | None]:
    op = constraint.get("operator", "between")
    minimum = constraint.get("min")
    maximum = constraint.get("max")
    typical = constraint.get("typ")
    if op == "lt":
        return (None, maximum if maximum is not None else typical)
    if op == "lte":
        return (None, maximum if maximum is not None else typical)
    if op == "gt":
        return (minimum if minimum is not None else typical, None)
    if op == "gte":
        return (minimum if minimum is not None else typical, None)
    if op == "eq":
        return (typical, typical)
    return (minimum, maximum)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/openapi.yaml", response_class=PlainTextResponse)
def openapi_file() -> str:
    return OPENAPI.read_text(encoding="utf-8")


@app.get("/api/parts")
def list_parts(
    family: str | None = Query(default=None),
    manufacturer: str | None = Query(default=None),
    package: str | None = Query(default=None),
    lifecycle_status: str | None = Query(default=None),
    in_stock: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    filt: dict[str, Any] = {"family": family, "manufacturer": manufacturer, "package": package}
    if lifecycle_status:
        filt["lifecycle_status"] = [s.strip() for s in lifecycle_status.split(",") if s.strip()]
    if q:
        filt["text"] = q
    parts = _match_filter(filt)
    window = parts[offset : offset + limit]
    return {
        "query": q,
        "filter": filt,
        "results": [_summary(p) for p in window],
        "total": len(parts),
        "limit": limit,
        "offset": offset,
        "took_ms": 4,
        "filter_explanation": "Fixture backed mock result.",
        "llm_used": False,
    }


@app.get("/api/parts/{part_id}")
def get_part(part_id: str) -> dict:
    for part in SEED_PARTS:
        if part["part_id"] == part_id:
            return {
                **part,
                "parameters": _parameter_values(part),
                "offers": [
                    {
                        "part_id": part_id,
                        "distributor": "DigiKey",
                        "sku": f"296-{part['mpn']}-ND",
                        "stock": 48213,
                        "unit_price": 0.89,
                        "currency": "USD",
                        "price_breaks": [{"quantity": 1, "price": 0.89}],
                        "fetched_at": _now.isoformat(),
                        "url": "https://www.digikey.com",
                    },
                    {
                        "part_id": part_id,
                        "distributor": "Mouser",
                        "sku": f"81-{part['mpn']}",
                        "stock": 12000,
                        "unit_price": 0.92,
                        "currency": "USD",
                        "price_breaks": [{"quantity": 1, "price": 0.92}],
                        "fetched_at": _now.isoformat(),
                        "url": "https://www.mouser.com",
                    },
                ],
                "updated_at": _now.isoformat(),
            }
    raise HTTPException(status_code=404, detail=f"part {part_id} not found")


@app.get("/api/parts/{part_id}/sources/{param_id}")
def get_parameter_source(part_id: str, param_id: str) -> dict:
    part = next((p for p in SEED_PARTS if p["part_id"] == part_id), None)
    if part is None:
        raise HTTPException(status_code=404, detail=f"part {part_id} not found")
    for value in _parameter_values(part):
        if value["param_id"] == param_id:
            return {
                "value": value,
                "source": {
                    "source_id": value["source_id"],
                    "url": f"https://example.invalid/api/{part['mpn']}",
                    "type": "api",
                    "fetched_at": _now.isoformat(),
                    "file_hash": None,
                    "distributor": "DigiKey",
                },
                "page_url": f"/api/sources/{value['source_id']}/page/{value['page']}",
                "page_text": None,
            }
    raise HTTPException(status_code=404, detail=f"param {param_id} not found")


@app.get("/api/sources/{source_id}/page/{n}")
def get_source_page(source_id: str, n: int, format: str = Query(default="meta")) -> Any:
    sample = next((s for s in PAGE_SAMPLES if s["source_id"] == source_id), None)
    if sample is None:
        for pdf_key, payload in EXPECTED_VALUES.items():
            if pdf_key.endswith(f"{source_id}.pdf") or payload.get("source_id") == source_id:
                sample = {
                    "source_id": source_id,
                    "page": n,
                    "text": "Absolute Maximum Ratings / Electrical Characteristics",
                    "is_image_only": False,
                }
                break
    if sample is None:
        raise HTTPException(status_code=404, detail=f"source {source_id} not found")
    if format == "image":
        # 1x1 transparent PNG placeholder.
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c6300010000050001"
            "0d0a2db40000000049454e44ae426082"
        )
        return Response(content=png, media_type="image/png")
    return {
        "source_id": source_id,
        "page": n,
        "width": 595,
        "height": 842,
        "text": sample.get("text"),
        "image_url": f"/api/sources/{source_id}/page/{n}?format=image",
        "is_image_only": bool(sample.get("is_image_only", False)),
    }


@app.post("/api/search")
def search_parts(payload: dict = Body(...)) -> dict:
    query = payload.get("query", "")
    filt = payload.get("filter")
    if not filt:
        filt = _guess_filter(query)
    parts = _match_filter(filt)
    limit = int(payload.get("limit", 50))
    offset = int(payload.get("offset", 0))
    window = parts[offset : offset + limit]
    return {
        "query": query,
        "filter": filt,
        "results": [_summary(p) for p in window],
        "total": len(parts),
        "limit": limit,
        "offset": offset,
        "took_ms": 7,
        "filter_explanation": f"Mock filter for '{query}'.",
        "llm_used": False,
    }


def _guess_filter(query: str) -> dict:
    """A tiny deterministic stand-in for the LLM filter builder."""
    text = query.lower()
    filt: dict[str, Any] = {}
    if "mosfet" in text:
        filt["family"] = "mosfet"
    elif "driver" in text:
        filt["family"] = "gate_driver"
    match = re.search(r"(\d+(?:\.\d+)?)\s*(v|volt)\b", text)
    if match:
        filt.setdefault("parameters", []).append(
            {
                "name": "vds_max",
                "unit": "V",
                "min": None,
                "max": float(match.group(1)),
                "typ": None,
                "operator": "lte",
            }
        )
    match = re.search(
        r"rds\(?on\)?\s*(?:below|under|<|max)?\s*(\d+(?:\.\d+)?)\s*(m|milli)?\s*(ohm|ohms)?", text
    )
    if match:
        value = float(match.group(1))
        unit = "mohm" if match.group(2) else "ohm"
        filt.setdefault("parameters", []).append(
            {
                "name": "rds_on",
                "unit": unit,
                "min": None,
                "max": value,
                "typ": None,
                "operator": "lte",
            }
        )
    return filt


@app.get("/api/parts/{part_id}/alternatives")
def get_alternatives(
    part_id: str, limit: int = Query(default=10, ge=1, le=50), explain: bool = Query(default=True)
) -> list[dict]:
    part = next((p for p in SEED_PARTS if p["part_id"] == part_id), None)
    if part is None:
        raise HTTPException(status_code=404, detail=f"part {part_id} not found")
    others = [
        p
        for p in SEED_PARTS
        if p["family"] == part["family"]
        and p["package"] == part["package"]
        and p["part_id"] != part_id
    ]
    if not others:
        others = [
            p for p in SEED_PARTS if p["family"] == part["family"] and p["part_id"] != part_id
        ]
    results = []
    for index, other in enumerate(others[:limit], start=1):
        results.append(
            {
                "part": _summary(other, score=round(1.0 - index * 0.1, 3)),
                "score": round(1.0 - index * 0.1, 3),
                "rank": index,
                "reason": "Lower Rds(on) and lower total gate charge.",
                "rejected": False,
                "rejection_reason": None,
                "differences": {
                    "rds_on": {
                        "reference": part["parameters"].get("rds_on", {}).get("value"),
                        "candidate": other["parameters"].get("rds_on", {}).get("value"),
                    }
                },
            }
        )
    return results


@app.post("/api/bom/check")
async def check_bom(request: Request) -> dict:
    content_type = request.headers.get("content-type", "")
    filename = None
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise HTTPException(status_code=422, detail="file is required")
        raw = await upload.read()
        filename = getattr(upload, "filename", None)
        text = raw.decode("utf-8", errors="replace")
    else:
        payload = await request.json()
        text = payload.get("content", "")
        filename = payload.get("filename")

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return {
            "filename": filename,
            "total_lines": 0,
            "matched_lines": 0,
            "unmatched_lines": 0,
            "risk_count": 0,
            "highest_severity": None,
            "lines": [],
            "risks": [],
            "took_ms": 2,
        }

    header = [h.strip().lower() for h in re.split(r"[,;\t]", lines[0])]
    mpn_index = 0
    for candidate in (
        "mpn",
        "part number",
        "partnumber",
        "manufacturer part number",
        "mfr part number",
    ):
        if candidate in header:
            mpn_index = header.index(candidate)
            break
    qty_index = next(
        (i for i, h in enumerate(header) if h in ("qty", "quantity", "quantity ordered")), None
    )
    mfr_index = next(
        (i for i, h in enumerate(header) if h in ("manufacturer", "mfr", "mfr name")), None
    )

    out_lines = []
    risks: list[dict] = []
    matched = 0
    for number, row in enumerate(lines[1:], start=2):
        cells = [c.strip() for c in re.split(r"[,;\t]", row)]
        if not cells or not any(cells):
            continue
        mpn = cells[mpn_index] if mpn_index < len(cells) else cells[0]
        quantity = 1
        if qty_index is not None and qty_index < len(cells):
            try:
                quantity = int(float(cells[qty_index]))
            except ValueError:
                quantity = 1
        manufacturer = (
            cells[mfr_index] if mfr_index is not None and mfr_index < len(cells) else None
        )

        part = next(
            (
                p
                for p in SEED_PARTS
                if p["mpn"].lower() == mpn.lower()
                and (not manufacturer or manufacturer.lower() in p["manufacturer"].lower())
            ),
            None,
        )
        line_risks: list[dict] = []
        if part is None:
            line_risks.append(
                {
                    "code": "not_found",
                    "severity": "high",
                    "message": f"No part matches MPN '{mpn}'.",
                    "part_id": None,
                    "mpn": mpn,
                    "suggestion": "Check the manufacturer part number.",
                }
            )
        else:
            matched += 1
            if part["lifecycle_status"] == "obsolete":
                line_risks.append(
                    {
                        "code": "obsolete",
                        "severity": "critical",
                        "message": f"{mpn} is obsolete.",
                        "part_id": part["part_id"],
                        "mpn": mpn,
                        "suggestion": "Use the alternatives list.",
                    }
                )
            elif part["lifecycle_status"] == "nrnd":
                line_risks.append(
                    {
                        "code": "nrnd",
                        "severity": "medium",
                        "message": f"{mpn} is NRND (not recommended for new designs).",
                        "part_id": part["part_id"],
                        "mpn": mpn,
                        "suggestion": "Plan a migration.",
                    }
                )
            if part["lifecycle_status"] != "active":
                line_risks.append(
                    {
                        "code": "single_source",
                        "severity": "low",
                        "message": f"{mpn} is only offered by one distributor in the cache.",
                        "part_id": part["part_id"],
                        "mpn": mpn,
                        "suggestion": "Qualify a second source.",
                    }
                )
        risks.extend(line_risks)
        out_lines.append(
            {
                "line_number": number,
                "mpn": mpn,
                "quantity": quantity,
                "manufacturer": manufacturer,
                "matched_part_id": part["part_id"] if part else None,
                "matched": part is not None,
                "risks": line_risks,
            }
        )

    severities = [r["severity"] for r in risks]
    order = ["info", "low", "medium", "high", "critical"]
    highest = max(severities, key=lambda s: order.index(s)) if severities else None
    return {
        "filename": filename,
        "total_lines": len(out_lines),
        "matched_lines": matched,
        "unmatched_lines": len(out_lines) - matched,
        "risk_count": len(risks),
        "highest_severity": highest,
        "lines": out_lines,
        "risks": risks,
        "took_ms": 3,
    }


@app.get("/api/review")
def list_review(
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)
) -> list[dict]:
    items: list[dict] = []
    for part in SEED_PARTS[:6]:
        for value in _parameter_values(part):
            if value["status"] != "review":
                continue
            items.append(
                {
                    "param_id": value["param_id"],
                    "part_id": part["part_id"],
                    "mpn": part["mpn"],
                    "manufacturer": part["manufacturer"],
                    "family": part["family"],
                    "name": value["name"],
                    "value": value["value"],
                    "value_min": value["value_min"],
                    "value_typ": value["value_typ"],
                    "value_max": value["value_max"],
                    "unit": value["unit"],
                    "condition": value["condition"],
                    "source_id": value["source_id"],
                    "page": value["page"],
                    "method": value["method"],
                    "confidence": 0.62,
                    "status": "review",
                    "reasons": ["confidence below the review threshold"],
                    "raw_text": value["raw_text"],
                    "created_at": _now.isoformat(),
                }
            )
    return items[offset : offset + limit]


@app.post("/api/review/{param_id}")
def decide_review(param_id: str, payload: dict = Body(...)) -> dict:
    action = payload.get("action", "accept")
    status = {"accept": "accepted", "correct": "accepted", "reject": "rejected"}[action]
    return {
        "param_id": param_id,
        "status": status,
        "message": f"Value {action}ed.",
        "item": None,
    }


_JOBS: dict[str, dict] = {}


@app.post("/api/jobs/extract")
def start_job(payload: dict = Body(default={})) -> dict:
    job_id = f"job-{len(_JOBS) + 1:04d}"
    status = {
        "job_id": job_id,
        "kind": "extract",
        "state": "queued",
        "progress": 0,
        "total": 1,
        "message": "Queued.",
        "part_id": payload.get("part_id"),
        "source_id": payload.get("source_id"),
        "result": None,
        "error": None,
        "created_at": _now.isoformat(),
        "updated_at": _now.isoformat(),
    }
    _JOBS[job_id] = status
    return status


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    status = _JOBS.get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    status["state"] = "completed"
    status["progress"] = 1
    status["message"] = "Done."
    return status


@app.get("/api/stats")
def get_stats() -> dict:
    by_family: dict[str, int] = {}
    by_lifecycle: dict[str, int] = {}
    by_manufacturer: dict[str, int] = {}
    for part in SEED_PARTS:
        by_family[part["family"]] = by_family.get(part["family"], 0) + 1
        by_lifecycle[part["lifecycle_status"]] = by_lifecycle.get(part["lifecycle_status"], 0) + 1
        by_manufacturer[part["manufacturer"]] = by_manufacturer.get(part["manufacturer"], 0) + 1
    total_params = sum(len(p.get("parameters", {})) for p in SEED_PARTS)
    return {
        "parts_total": len(SEED_PARTS),
        "parts_by_family": by_family,
        "parts_by_lifecycle": by_lifecycle,
        "parts_by_manufacturer": by_manufacturer,
        "parameters_total": total_params,
        "values_by_status": {"accepted": int(total_params * 0.86), "review": 42, "rejected": 9},
        "values_by_method": {"tier1": int(total_params * 0.8), "tier2": 38, "tier3": 5, "api": 20},
        "review_pending": 42,
        "sources_total": len(SEED_PARTS) * 2,
        "coverage_pct": round(100 * 0.86, 1),
        "mean_confidence": 0.88,
        "llm_calls_total": 128,
        "llm_tokens_in": 412_000,
        "llm_tokens_out": 96_000,
        "llm_cost_total": 3.42,
        "avg_cost_per_datasheet": 0.11,
        "accuracy": {"mosfet": 0.91, "gate_driver": 0.84},
        "generated_at": _now.isoformat(),
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")

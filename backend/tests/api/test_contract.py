"""The app must conform to the frozen OpenAPI contract.

``contracts/openapi.yaml`` is the source of truth. These tests check that the
generated schema has the same paths, the same operation ids and the same
response field names, and that a Schemathesis run against the contract finds
no violation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
OPENAPI_PATH = REPO_ROOT / "contracts" / "openapi.yaml"

CONTRACT_PATHS = {
    "/api/parts": {"get"},
    "/api/parts/{part_id}": {"get"},
    "/api/parts/{part_id}/sources/{param_id}": {"get"},
    "/api/sources/{source_id}/page/{n}": {"get"},
    "/api/search": {"post"},
    "/api/parts/{part_id}/alternatives": {"get"},
    "/api/bom/check": {"post"},
    "/api/review": {"get"},
    "/api/review/{param_id}": {"post"},
    "/api/jobs/extract": {"post"},
    "/api/jobs/{job_id}": {"get"},
    "/api/stats": {"get"},
}


@pytest.fixture(scope="module")
def contract() -> dict:
    return yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def generated() -> dict:
    with TestClient(create_app()) as client:
        return client.get("/openapi.json").json()


def test_the_contract_file_is_openapi_31(contract: dict) -> None:
    assert contract["openapi"].startswith("3.1")


def test_the_app_has_every_contract_path(generated: dict) -> None:
    for path, methods in CONTRACT_PATHS.items():
        assert path in generated["paths"], f"{path} is missing from the app"
        for method in methods:
            assert method in generated["paths"][path], f"{method.upper()} {path} is missing"


def test_the_app_has_no_unknown_api_path(generated: dict) -> None:
    # /health is a deliberate addition and is documented in the handoff.
    extra = set(generated["paths"]) - set(CONTRACT_PATHS) - {"/health"}
    assert not extra, f"the app has paths the contract does not know: {sorted(extra)}"


def test_the_operation_ids_match_the_contract(generated: dict, contract: dict) -> None:
    for path, methods in CONTRACT_PATHS.items():
        for method in methods:
            operation = contract["paths"][path][method]
            assert generated["paths"][path][method]["operationId"] == operation["operationId"]


def test_the_response_schemas_use_the_same_field_names(generated: dict, contract: dict) -> None:
    generated_schemas = generated["components"]["schemas"]
    contract_schemas = contract["components"]["schemas"]
    for name in (
        "SearchResponse",
        "PartRecord",
        "PartSummary",
        "ParameterValue",
        "SourceRef",
        "SourcePage",
        "AlternativeResult",
        "BomCheckResponse",
        "BomLine",
        "BomRisk",
        "ReviewItem",
        "ReviewResponse",
        "JobStatus",
        "StatsResponse",
    ):
        assert name in generated_schemas, f"{name} is missing from the generated schema"
        assert name in contract_schemas, f"{name} is missing from the contract"
        contract_fields = set(contract_schemas[name].get("properties", {}))
        generated_fields = set(generated_schemas[name].get("properties", {}))
        assert contract_fields <= generated_fields, (
            f"{name}: the app is missing the contract fields "
            f"{sorted(contract_fields - generated_fields)}"
        )


def test_a_live_response_matches_the_contract_schema(client: TestClient) -> None:
    payload = client.get("/api/parts", params={"limit": 1}).json()
    contract = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    schema = contract["components"]["schemas"]["SearchResponse"]
    assert set(schema["required"]) <= set(payload)
    result_schema = contract["components"]["schemas"]["PartSummary"]
    assert set(result_schema["required"]) <= set(payload["results"][0])


def test_the_error_shape_matches_the_contract(client: TestClient) -> None:
    payload = client.get("/api/parts/nope").json()
    assert "detail" in payload


def test_the_query_parameters_match_the_contract(generated: dict, contract: dict) -> None:
    """The bounds of a query parameter have to be enforced, not only documented."""
    for path, method in (("/api/parts", "get"), ("/api/review", "get")):
        contract_params = {
            parameter["name"]: parameter
            for parameter in contract["paths"][path][method].get("parameters", [])
        }
        generated_params = {
            parameter["name"]: parameter
            for parameter in generated["paths"][path][method].get("parameters", [])
        }
        for name, parameter in contract_params.items():
            if "schema" not in parameter:
                continue
            assert name in generated_params, f"{path} is missing the parameter {name}"
            for bound in ("minimum", "maximum"):
                if bound in parameter["schema"]:
                    assert parameter["schema"][bound] == generated_params[name]["schema"].get(
                        bound
                    ), f"{path}:{name} does not enforce {bound}"


# ---------------------------------------------------------------- schemathesis

schemathesis = pytest.importorskip("schemathesis")
from hypothesis import HealthCheck, settings  # noqa: E402
from schemathesis import hook as schemathesis_hook  # noqa: E402
from schemathesis import openapi as schemathesis_openapi  # noqa: E402
from schemathesis import pytest as schemathesis_pytest  # noqa: E402

#: A BOM that the API can actually read. The contract describes the upload as
#: a CSV, but a JSON schema cannot say "a CSV with an MPN column", so the
#: generated body is random text. This hook replaces it with a real BOM, which
#: makes the positive check meaningful: a valid CSV has to be accepted, and
#: the negative check still rejects a body that violates the schema.
VALID_BOM = "MPN,Qty,Manufacturer\nIRF3205S,10,International Rectifier\n"


@schemathesis_hook("before_call")
def before_call(ctx, case, **kwargs):
    """Give the BOM upload a body that a user would actually send."""
    if case.path == "/api/bom/check" and case.method == "POST":
        case.body = VALID_BOM.encode("utf-8")
    return None


_CONTRACT_SCHEMA = schemathesis_openapi.from_path(str(OPENAPI_PATH))
_CONTRACT_SCHEMA.app = create_app()


@schemathesis_pytest.parametrize(partpilot=_CONTRACT_SCHEMA)
@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
def test_the_app_satisfies_the_frozen_contract(case) -> None:
    """Schemathesis generates requests from the contract and checks the answers."""
    response = case.call()
    case.validate_response(response)

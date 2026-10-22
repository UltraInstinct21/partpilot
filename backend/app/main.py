"""The PartPilot API.

    uvicorn app.main:app --reload

The application is built by :func:`create_app`. It uses the in-memory fakes
of :mod:`app.fakes` until the real modules are integrated; see
:mod:`app.wiring` for the one file that has to change.

The API never calls a distributor API or an LLM from the browser: every
distributor and model call happens on the server (NFR-02, NFR-07).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.container import Container
from app.errors import register_exception_handlers
from app.rate_limit import FixedWindowRateLimiter
from app.routes import ROUTERS
from app.schemas import HealthResponse
from app.wiring import build_container
from shared.config import Settings, get_settings

DESCRIPTION = """
PartPilot - AI-assisted component data mining for power MOSFETs and gate drivers.

**Contract v1.** This API is described by the frozen `contracts/openapi.yaml`.

The API never calls a distributor API or an LLM from the browser. Every value
returned here carries its provenance: `source_id`, `page`, `method` (the
extraction tier), `confidence`, `status` and the test `condition`.
"""

#: The methods the frontend is allowed to use.
ALLOWED_METHODS = ["GET", "POST", "OPTIONS"]

#: The headers the frontend is allowed to send.
ALLOWED_HEADERS = ["Accept", "Content-Type", "Authorization", "X-Requested-With"]

#: The headers the frontend may read from a response.
EXPOSED_HEADERS = ["Retry-After", "Content-Length", "Content-Type"]

#: Parameter constraints of the frozen contract that the API does not enforce
#: with a 422 (the contract documents no 422 for those endpoints), but that
#: still belong into the generated schema.
PARAMETER_OVERRIDES: dict[tuple[str, str, str], dict[str, object]] = {
    ("/api/parts", "get", "limit"): {"minimum": 1, "maximum": 500, "default": 50},
    ("/api/parts", "get", "offset"): {"minimum": 0, "default": 0},
    ("/api/parts/{part_id}/alternatives", "get", "limit"): {
        "minimum": 1,
        "maximum": 50,
        "default": 10,
    },
    ("/api/review", "get", "limit"): {"minimum": 1, "maximum": 200, "default": 50},
    ("/api/review", "get", "offset"): {"minimum": 0, "default": 0},
    ("/api/sources/{source_id}/page/{n}", "get", "n"): {"minimum": 1},
    ("/api/sources/{source_id}/page/{n}", "get", "format"): {
        "enum": ["meta", "image"],
        "default": "meta",
    },
}


def customise_openapi(schema: dict) -> dict:
    """Add the parameter constraints of the frozen contract to the schema."""
    paths = schema.get("paths", {})
    for (path, method, name), overrides in PARAMETER_OVERRIDES.items():
        operation = paths.get(path, {}).get(method)
        if not operation:
            continue
        for parameter in operation.get("parameters", []):
            if parameter.get("name") == name:
                parameter.setdefault("schema", {}).update(overrides)
    return schema


def create_app(
    container: Container | None = None,
    settings: Settings | None = None,
    rate_limiter: FixedWindowRateLimiter | None = None,
) -> FastAPI:
    """Build the FastAPI application.

    Args:
        container: An optional container; a new one is built when it is ``None``.
        settings: The runtime settings; the cached ones are used by default.
        rate_limiter: An optional rate limiter for ``POST /api/search``. A test
            uses it to lower the budget.
    """
    settings = settings or get_settings()
    application = FastAPI(
        title="PartPilot API",
        version="1.0.0",
        description=DESCRIPTION,
        license_info={"name": "MIT"},
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
        expose_headers=EXPOSED_HEADERS,
    )

    register_exception_handlers(application)

    for router in ROUTERS:
        application.include_router(router)

    @application.get(
        "/health",
        response_model=HealthResponse,
        operation_id="health",
        summary="Liveness probe (not part of the frozen contract)",
        tags=["health"],
    )
    def health() -> HealthResponse:
        """Return the liveness of the API."""
        return HealthResponse(status="ok")

    if container is not None:
        application.state.container = container
    else:
        application.state.container = build_container(settings, rate_limiter=rate_limiter)

    def openapi() -> dict:
        """The generated OpenAPI schema, aligned with the frozen contract."""
        if application.openapi_schema:
            return application.openapi_schema
        schema = get_openapi(
            title=application.title,
            version=application.version,
            description=application.description,
            routes=application.routes,
            license_info=application.license_info,
        )
        application.openapi_schema = customise_openapi(schema)
        return application.openapi_schema

    application.openapi = openapi  # type: ignore[method-assign]
    return application


#: The application that ``uvicorn app.main:app`` serves.
app = create_app()


__all__ = ["ALLOWED_HEADERS", "ALLOWED_METHODS", "EXPOSED_HEADERS", "app", "create_app"]

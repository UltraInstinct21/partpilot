"""Error handling for the PartPilot API.

Every error leaves the API in the shape of the frozen ``Error`` schema:
``{"detail": "...", "code": "..."}``. The ``detail`` is always a *string* -
the frozen contract says so - so FastAPI's default validation error list is
replaced here.

No stack trace, no secret and no internal path ever reaches the client.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("partpilot.api")


def _error(status_code: int, detail: str, code: str | None = None) -> JSONResponse:
    """Build the JSON body of an error response."""
    payload: dict[str, str | None] = {"detail": detail}
    if code:
        payload["code"] = code
    return JSONResponse(status_code=status_code, content=payload)


def _summarise_validation_errors(exc: RequestValidationError) -> str:
    """Turn the FastAPI validation error list into one short sentence."""
    parts: list[str] = []
    for error in exc.errors()[:5]:
        location = ".".join(str(item) for item in error.get("loc", ()) if item != "body")
        message = str(error.get("msg", "invalid value"))
        parts.append(f"{location}: {message}" if location else message)
    if not parts:
        return "The request did not validate."
    return "Invalid request - " + "; ".join(parts)


def register_exception_handlers(app: FastAPI) -> None:
    """Install the global handlers on ``app``."""

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # 422 is used as a literal: the name of the constant changed in Starlette.
        return _error(422, _summarise_validation_errors(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        status_code = exc.status_code
        # FastAPI reports a body that is not valid JSON as a 400. A body that
        # cannot be parsed is a validation problem, so it gets the same 422 as
        # every other invalid input. The frozen contract documents one status
        # for an invalid request.
        if status_code == 400 and detail == "There was an error parsing the body":
            status_code = 422
            detail = "The request body is not valid JSON."
        headers = getattr(exc, "headers", None)
        response = _error(status_code, detail)
        if headers:
            response.headers.update(headers)
        return response

    @app.exception_handler(HTTPException)
    async def _fastapi_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return await _http_error(request, exc)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Log the real error on the server, but never leak it to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "The server could not complete the request.",
            code="internal_error",
        )


__all__ = ["register_exception_handlers"]

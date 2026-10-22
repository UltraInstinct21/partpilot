"""Natural-language parametric search (``POST /api/search``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import get_rate_limiter, get_search_service
from app.rate_limit import FixedWindowRateLimiter
from shared.interfaces import SearchService
from shared.schemas import SearchRequest, SearchResponse

router = APIRouter(prefix="/api", tags=["search"])


def client_key(request: Request) -> str:
    """The key of the rate limiter: the IP of the client."""
    client = request.client
    if client is not None and client.host:
        return client.host
    return request.headers.get("x-forwarded-for", "unknown").split(",")[0].strip() or "unknown"


@router.post(
    "/search",
    response_model=SearchResponse,
    operation_id="searchParts",
    summary="Natural-language parametric search",
    description=(
        "The query is turned into a validated `SearchFilter` by the LLM and the "
        "filter is executed by the database. The LLM never chooses the result "
        "rows. When `filter` is supplied the query is not sent to the LLM at all "
        "(rate limited endpoint, plan WP6)."
    ),
    responses={
        422: {"description": "The request body did not validate."},
        429: {"description": "Too many search requests. The LLM budget is protected."},
    },
)
def search_parts(
    payload: SearchRequest,
    request: Request,
    service: SearchService = Depends(get_search_service),
    limiter: FixedWindowRateLimiter = Depends(get_rate_limiter),
) -> SearchResponse:
    """Search the catalogue with a natural-language query or with a filter."""
    decision = limiter.check(client_key(request))
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                "Too many search requests. The limit is "
                f"{decision.limit} requests per minute - please retry later."
            ),
            headers={"Retry-After": str(decision.retry_after)},
        )

    if payload.filter is not None:
        # A filter was supplied: the query is not sent to the LLM at all.
        response = service.search_filter(payload.filter, limit=payload.limit, offset=payload.offset)
        response.query = payload.query
        response.llm_used = False
        return response

    # The service knows whether the model built the filter or the
    # deterministic fallback did, so the flag is not overwritten here.
    return service.search(payload.query, limit=payload.limit, offset=payload.offset)


__all__ = ["client_key", "router"]

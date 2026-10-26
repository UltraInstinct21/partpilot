"""Natural-language parametric search (``POST /api/search``)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.dependencies import get_rate_limiter, get_search_service
from app.rate_limit import FixedWindowRateLimiter
from services.advisor import AIAdvisory, ComponentAdvisorService
from shared.interfaces import SearchService
from shared.schemas import SearchRequest, SearchResponse

router = APIRouter(prefix="/api", tags=["search"])


class AdviseRequest(BaseModel):
    query: str = Field(min_length=1, description="Question or component to evaluate")


@router.post(
    "/search/advise",
    include_in_schema=False,
    response_model=AIAdvisory,
    operation_id="adviseOnSearch",
    summary="AI Engineering Judgment & Recommendations",
)
def advise_on_search(
    payload: AdviseRequest,
    service: SearchService = Depends(get_search_service),
) -> AIAdvisory:
    """Provide AI hardware engineering judgment, tradeoffs, and recommendations for a component query."""
    advisor = ComponentAdvisorService(service._repository)  # type: ignore[attr-defined]
    advisory = advisor.get_advisory(payload.query)
    if not advisory:
        raise HTTPException(status_code=400, detail="Could not generate advisory for this query.")
    return advisory


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


@router.post(
    "/search/stream",
    include_in_schema=False,
    summary="Progressive streaming natural-language parametric search",
    description=(
        "Streams search results progressively via Server-Sent Events (SSE). "
        "Emits filter immediately, followed by local catalogue matches (zero-wait), "
        "live web/provider discoveries, and advisory in real time."
    ),
)
def stream_search_parts(
    payload: SearchRequest,
    request: Request,
    service: SearchService = Depends(get_search_service),
    limiter: FixedWindowRateLimiter = Depends(get_rate_limiter),
):
    """Progressive SSE streaming search (reduces perceived waiting time)."""
    decision = limiter.check(client_key(request))
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many search requests. The limit is {decision.limit} requests per minute."
            ),
            headers={"Retry-After": str(decision.retry_after)},
        )

    def event_generator():
        stream_fn = getattr(service, "stream_search", None)
        if callable(stream_fn):
            for event in stream_fn(payload.query, limit=payload.limit, offset=payload.offset):
                yield f"data: {json.dumps(event)}\n\n"
        else:
            res = service.search(payload.query, limit=payload.limit, offset=payload.offset)
            yield f"data: {json.dumps({'type': 'done', 'results': [p.model_dump() for p in res.results], 'total': res.total})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/search/stream",
    include_in_schema=False,
    summary="Progressive streaming search via GET EventSource",
)
def stream_search_parts_get(
    request: Request,
    q: str = Query(default="", description="Search query"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: SearchService = Depends(get_search_service),
    limiter: FixedWindowRateLimiter = Depends(get_rate_limiter),
):
    """GET SSE streaming search for EventSource compatibility."""
    return stream_search_parts(
        SearchRequest(query=q, limit=limit, offset=offset),
        request=request,
        service=service,
        limiter=limiter,
    )


__all__ = ["client_key", "router"]

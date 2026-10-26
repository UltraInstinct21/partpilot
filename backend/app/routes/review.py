"""The review queue for low-confidence values (``/api/review``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import get_repository, get_review_service
from services.advisor import ComponentAdvisorService, ReviewAdvisoryResponse, ReviewPartCandidate
from shared.interfaces import PartsRepository, ReviewService
from shared.schemas import ReviewDecision, ReviewItem, ReviewResponse

router = APIRouter(prefix="/api", tags=["review"])


class ReviewAdvisoryRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    parts: list[ReviewPartCandidate] = Field(default_factory=list)
    priority: str = Field(default="balanced", description="balanced, efficiency, cost, thermal, supply")
    custom_query: str | None = Field(default=None, description="Custom engineering constraint or question")


@router.post(
    "/review/advisory",
    response_model=ReviewAdvisoryResponse,
    operation_id="reviewAdvisory",
    summary="AI Recommendations and Tradeoffs for Review Queue candidates",
    include_in_schema=False,
)
@router.post(
    "/review/analyze",
    response_model=ReviewAdvisoryResponse,
    include_in_schema=False,
)
def review_advisory(
    payload: ReviewAdvisoryRequest,
    repository: PartsRepository = Depends(get_repository),
) -> ReviewAdvisoryResponse:
    """Evaluate candidate parts in review queue for tradeoffs, recommendations, and BOM readiness."""
    advisor = ComponentAdvisorService(repository)
    return advisor.analyze_review_candidates(
        candidates=payload.parts,
        priority=payload.priority,
        custom_query=payload.custom_query,
    )




@router.get(
    "/review",
    response_model=list[ReviewItem],
    operation_id="listReviewQueue",
    summary="List the values in the review queue",
)
def list_review_queue(
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="How many entries to return (1-200).",
    ),
    offset: int = Query(default=0, ge=0, description="How many entries to skip."),
    service: ReviewService = Depends(get_review_service),
) -> list[ReviewItem]:
    """Return the values that wait for a human decision."""
    # The bounds are enforced by the typed parameter, so the generated schema
    # carries them and an out-of-range value is a 422, exactly like the
    # frozen contract documents.
    return service.queue(limit=limit, offset=offset)


@router.post(
    "/review/{param_id}",
    response_model=ReviewResponse,
    operation_id="decideReview",
    summary="Accept or correct one reviewed value",
    responses={
        404: {"description": "The value does not exist."},
        422: {"description": "The decision did not validate."},
    },
)
def decide_review(
    payload: ReviewDecision,
    param_id: str = Path(description="The identifier of the value."),
    service: ReviewService = Depends(get_review_service),
) -> ReviewResponse:
    """Apply a human decision to one reviewed value."""
    try:
        return service.decide(param_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Value '{param_id}' was not found.") from exc


__all__ = ["router"]

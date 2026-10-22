"""The review queue for low-confidence values (``/api/review``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.dependencies import get_review_service
from shared.interfaces import ReviewService
from shared.schemas import ReviewDecision, ReviewItem, ReviewResponse

router = APIRouter(prefix="/api", tags=["review"])


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

"""Review queue operations (plan WP6, FR-10).

The service is a thin, well tested wrapper around the repository: the
repository owns the data, the service owns the wording of the answer.
"""

from __future__ import annotations

from shared.interfaces import PartsRepository
from shared.schemas import (
    ReviewDecision,
    ReviewItem,
    ReviewResponse,
    ValueStatus,
)

__all__ = ["ReviewService"]

_ACTION_MESSAGES: dict[str, str] = {
    "accept": "Value accepted.",
    "correct": "Value corrected and stored.",
    "reject": "Value rejected.",
}


class ReviewService:
    """List and decide the values that wait for a person (FR-10).

    Args:
        repository: the injected :class:`~shared.interfaces.PartsRepository`.
    """

    def __init__(self, repository: PartsRepository) -> None:
        self._repository = repository

    def queue(self, limit: int = 50, offset: int = 0) -> list[ReviewItem]:
        """Return the review queue."""
        items = self._repository.list_review_queue(limit=limit, offset=offset)
        return list(items)

    def decide(self, param_id: str, decision: ReviewDecision) -> ReviewResponse:
        """Apply a human decision to one reviewed value."""
        response = self._repository.apply_review(param_id, decision)
        message = (response.message or "").strip()
        if not message:
            message = _ACTION_MESSAGES.get(decision.action, "Review applied.")
        if response.status == ValueStatus.REJECTED and decision.action != "reject":
            message = "The value was rejected by the validator."
        return ReviewResponse(
            param_id=response.param_id or param_id,
            status=response.status,
            message=message,
            item=response.item,
        )

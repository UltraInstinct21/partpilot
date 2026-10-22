"""Ranked alternatives (``/api/parts/{part_id}/alternatives``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.dependencies import get_alternatives_service, get_repository
from shared.interfaces import AlternativesService, PartsRepository
from shared.schemas import AlternativeResult

router = APIRouter(prefix="/api", tags=["alternatives"])


@router.get(
    "/parts/{part_id}/alternatives",
    response_model=list[AlternativeResult],
    operation_id="getAlternatives",
    summary="Get ranked alternative parts",
    responses={404: {"description": "The part does not exist."}},
)
def get_alternatives(
    part_id: str = Path(description="The identifier of the part."),
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
        description="How many alternatives to return (1-50).",
    ),
    explain: bool = Query(default=True, description="Ask for a one sentence trade-off summary."),
    service: AlternativesService = Depends(get_alternatives_service),
    repository: PartsRepository = Depends(get_repository),
) -> list[AlternativeResult]:
    """Return the alternatives of a part, best match first."""
    if repository.get_part(part_id) is None:
        raise HTTPException(status_code=404, detail=f"Part '{part_id}' was not found.")
    try:
        return service.alternatives(part_id, limit=limit, explain=explain)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Part '{part_id}' was not found.") from exc


__all__ = ["router"]

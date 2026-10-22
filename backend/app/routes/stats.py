"""Dashboard counters (``/api/stats``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_stats_service
from shared.interfaces import StatsService
from shared.schemas import StatsResponse

router = APIRouter(prefix="/api", tags=["stats"])


@router.get(
    "/stats",
    response_model=StatsResponse,
    operation_id="getStats",
    summary="Get counts and quality numbers",
)
def get_stats(service: StatsService = Depends(get_stats_service)) -> StatsResponse:
    """Return the dashboard numbers."""
    return service.stats()


__all__ = ["router"]

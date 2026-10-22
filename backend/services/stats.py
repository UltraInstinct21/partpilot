"""Dashboard statistics (plan WP7/WP8).

The numbers are computed by the repository (it owns the data); the service
only forwards the call and keeps the shape stable for the API layer.
"""

from __future__ import annotations

from shared.interfaces import PartsRepository
from shared.schemas import StatsResponse

__all__ = ["StatsService"]


class StatsService:
    """Return the dashboard counts and quality numbers.

    Args:
        repository: the injected :class:`~shared.interfaces.PartsRepository`.
    """

    def __init__(self, repository: PartsRepository) -> None:
        self._repository = repository

    def stats(self) -> StatsResponse:
        """Return the counts and quality numbers."""
        return self._repository.stats()

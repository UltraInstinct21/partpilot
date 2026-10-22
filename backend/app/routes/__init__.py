"""The routers of the PartPilot API."""

from __future__ import annotations

from fastapi import APIRouter

from app.routes import (
    alternatives,
    bom,
    jobs,
    parts,
    review,
    search,
    sources,
    stats,
)

#: Every router of the API, in the order of the frozen contract.
ROUTERS: list[APIRouter] = [
    parts.router,
    sources.router,
    search.router,
    alternatives.router,
    bom.router,
    review.router,
    jobs.router,
    stats.router,
]

__all__ = ["ROUTERS"]

"""Part catalogue routes (``/api/parts``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.dependencies import get_repository, get_search_service
from shared.interfaces import PartsRepository, SearchService
from shared.schemas import (
    Family,
    LifecycleStatus,
    PartRecord,
    SearchFilter,
    SearchResponse,
)

router = APIRouter(prefix="/api", tags=["parts"])


def parse_lifecycle_status(raw: str | None) -> list[LifecycleStatus]:
    """Parse the comma separated ``lifecycle_status`` query parameter."""
    if not raw:
        return []
    statuses: list[LifecycleStatus] = []
    for item in raw.split(","):
        name = item.strip().lower()
        if not name:
            continue
        try:
            statuses.append(LifecycleStatus(name))
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Unknown lifecycle status '{name}'. "
                    f"Valid values: {', '.join(item.value for item in LifecycleStatus)}."
                ),
            ) from exc
    return statuses


@router.get(
    "/parts",
    response_model=SearchResponse,
    operation_id="listParts",
    summary="List parts with filters",
)
def list_parts(
    service: SearchService = Depends(get_search_service),
    family: Family | None = Query(default=None, description="Restrict to one family."),
    manufacturer: str | None = Query(default=None),
    manufacturers: str | None = Query(default=None, description="Comma separated manufacturers."),
    package: str | None = Query(default=None),
    packages: str | None = Query(default=None, description="Comma separated list of packages."),
    lifecycle_status: str | None = Query(
        default=None, description="Comma separated list of lifecycle states."
    ),
    in_stock: bool | None = Query(default=None),
    q: str | None = Query(
        default=None, description="Free text filter over MPN, manufacturer and description."
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> SearchResponse:
    """Return a page of parts that match the filters."""
    pkg_list = (
        [p.strip() for p in packages.split(",") if p.strip()]
        if packages
        else ([package] if package else [])
    )
    mfr_list = (
        [m.strip() for m in manufacturers.split(",") if m.strip()]
        if manufacturers
        else ([manufacturer] if manufacturer else [])
    )
    filt = SearchFilter(
        family=family,
        manufacturer=manufacturer,
        manufacturer_in=mfr_list,
        package=package,
        package_in=pkg_list,
        lifecycle_status=parse_lifecycle_status(lifecycle_status),
        in_stock=in_stock,
        text=q,
    )
    return service.search_filter(filt, limit=limit, offset=offset)


@router.get(
    "/parts/{part_id}",
    response_model=PartRecord,
    operation_id="getPart",
    summary="Get one part with all of its values",
)
def get_part(
    part_id: str = Path(description="The identifier of the part."),
    repository: PartsRepository = Depends(get_repository),
) -> PartRecord:
    """Return one part with every value and offer (triggers deep scraping on-demand for web parts)."""
    part = repository.get_part(part_id)
    if part is None:
        raise HTTPException(status_code=404, detail=f"Part '{part_id}' was not found.")

    # Live scrape & enrich fields on-demand (multi-distributor offers, missing specs, verified datasheet PDF)
    try:
        from services.web_search import WebDiscoveryService
        from shared.config import get_settings

        settings = get_settings()
        web = WebDiscoveryService(settings.searxng_url, repository=repository)
        enriched = web.deep_scrape_part(part_id)
        if enriched is not None:
            return enriched
    except Exception as exc:
        pass

    return part


__all__ = ["parse_lifecycle_status", "router"]

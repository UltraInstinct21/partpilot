"""Provenance routes: the source of a value and the pages of a datasheet."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from app.dependencies import get_repository
from app.pdf import render_page_png
from app.schemas import ParameterSource
from shared.interfaces import PartsRepository
from shared.schemas import SourcePage

router = APIRouter(prefix="/api", tags=["sources"])


@router.get(
    "/parts/{part_id}/sources/{param_id}",
    response_model=ParameterSource,
    operation_id="getParameterSource",
    summary="Get the source of one value",
)
def get_parameter_source(
    part_id: str = Path(description="The identifier of the part."),
    param_id: str = Path(description="The identifier of the value."),
    repository: PartsRepository = Depends(get_repository),
) -> ParameterSource:
    """Return one value together with the source it was read from."""
    part = repository.get_part(part_id)
    if part is None:
        raise HTTPException(status_code=404, detail=f"Part '{part_id}' was not found.")
    value = repository.get_parameter(param_id)
    if value is None or value.part_id != part_id:
        raise HTTPException(status_code=404, detail=f"Value '{param_id}' was not found.")
    if not value.source_id:
        raise HTTPException(status_code=404, detail=f"Value '{param_id}' has no source.")
    source = repository.get_source(value.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source '{value.source_id}' was not found.")
    page_url = None
    page_text = None
    if value.page:
        page_url = f"/api/sources/{source.source_id}/page/{value.page}?format=image"
        page = repository.get_source_page(source.source_id, value.page)
        if page is not None:
            page_text = page.text
    return ParameterSource(
        value=value,
        source=source,
        page_url=page_url,
        page_text=page_text,
    )


@router.get(
    "/sources/{source_id}/page/{n}",
    response_model=SourcePage,
    operation_id="getSourcePage",
    summary="Get one page of a source",
    description=(
        "Returns the page metadata and the extracted text of page `n` (1-based). "
        "The `image_url` points at a rendered PNG of the same page so the frontend "
        "can show the datasheet page next to the value (FR-12)."
    ),
    responses={
        200: {
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/SourcePage"}},
                "image/png": {"schema": {"type": "string", "format": "binary"}},
            }
        },
        404: {"description": "The source or the page does not exist."},
    },
)
def get_source_page(
    source_id: str = Path(description="The identifier of the source."),
    n: int = Path(ge=1, description="The 1-based page number."),
    format: Literal["meta", "image"] = Query(  # noqa: A002 - the query parameter is called "format"
        default="meta",
        alias="format",
        description="meta (default) returns JSON, image returns the rendered PNG.",
    ),
    repository: PartsRepository = Depends(get_repository),
) -> SourcePage | Response:
    """Return one page of a source as JSON or as a rendered PNG."""
    source = repository.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' was not found.")
    page_number = n
    if format == "image":
        png = render_page_png(source.local_path, page_number)
        if png is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Page {page_number} of source '{source_id}' is not available as an image."
                ),
            )
        return Response(content=png, media_type="image/png")
    # Every format other than "image" returns the page metadata.
    page = repository.get_source_page(source_id, page_number)
    if page is None:
        raise HTTPException(
            status_code=404, detail=f"Page {page_number} of source '{source_id}' was not found."
        )
    if not page.image_url:
        # The URL of the rendered page is an API concern, so the route fills
        # it in. The frontend shows it next to the value (FR-12).
        page.image_url = f"/api/sources/{source_id}/page/{page_number}?format=image"
    return page


__all__ = ["router"]

"""BOM health check (``POST /api/bom/check``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from app.dependencies import get_bom_service, get_settings_dep
from shared.config import Settings
from shared.interfaces import BomService
from shared.schemas import BomCheckRequest, BomCheckResponse

router = APIRouter(prefix="/api", tags=["bom"])

#: Content types that are accepted for a BOM upload.
CSV_CONTENT_TYPES = frozenset(
    {
        "text/csv",
        "application/csv",
        "text/plain",
        "application/vnd.ms-excel",
    }
)


@router.post(
    "/bom/check",
    response_model=BomCheckResponse,
    operation_id="checkBom",
    summary="Upload a BOM CSV and get the risk table",
    responses={
        413: {"description": "The upload is larger than the configured limit."},
        422: {"description": "The upload is not a CSV file."},
    },
)
async def check_bom(
    request: Request,
    service: BomService = Depends(get_bom_service),
    settings: Settings = Depends(get_settings_dep),
) -> BomCheckResponse:
    """Check a BOM: either a multipart upload or a JSON body with the CSV text."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=(f"The upload is larger than the limit of {settings.max_upload_bytes} bytes."),
        )

    body = await request.body()
    if len(body) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"The upload is larger than the limit of {settings.max_upload_bytes} bytes.",
        )

    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()

    if content_type == "multipart/form-data":
        return await _check_multipart(request, service, settings)
    if content_type in {"application/json", "text/json", ""}:
        return _check_json(body, service)
    raise HTTPException(
        status_code=422,
        detail=(
            "The BOM must be sent as multipart/form-data with a 'file' field or as "
            "application/json with the CSV in 'content'."
        ),
    )


async def _check_multipart(
    request: Request,
    service: BomService,
    settings: Settings,
) -> BomCheckResponse:
    """Handle the multipart upload."""
    form = await request.form()
    upload = form.get("file")
    if upload is None:
        raise HTTPException(status_code=422, detail="A CSV file is required in the 'file' field.")
    if isinstance(upload, str):
        # A part without a filename is a plain form field. Its value is the
        # CSV text itself.
        if len(upload.encode("utf-8")) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"The upload is larger than the limit of {settings.max_upload_bytes} bytes."
                ),
            )
        return _run(service, upload, "bom.csv")
    filename = getattr(upload, "filename", None) or "bom.csv"
    upload_type = (getattr(upload, "content_type", "") or "").lower()
    if upload_type not in CSV_CONTENT_TYPES and not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=422,
            detail=f"Only CSV files are accepted (got '{upload_type or 'unknown'}').",
        )
    raw = await upload.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"The upload is larger than the limit of {settings.max_upload_bytes} bytes.",
        )
    text = raw.decode("utf-8", errors="replace")
    return _run(service, text, filename)


def _check_json(body: bytes, service: BomService) -> BomCheckResponse:
    """Handle the JSON body."""
    if not body.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "A BOM is required: send multipart/form-data with a 'file' field or "
                "application/json with the CSV in 'content'."
            ),
        )
    try:
        payload = BomCheckRequest.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="The BOM payload is not valid.") from exc
    return _run(service, payload.content or "", payload.filename)


def _run(service: BomService, content: str, filename: str | None) -> BomCheckResponse:
    """Run the BOM service and translate its errors into HTTP errors."""
    try:
        return service.check_csv(content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["CSV_CONTENT_TYPES", "router"]

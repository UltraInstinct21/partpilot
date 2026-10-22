"""API-local Pydantic models.

Every payload that crosses the API boundary is defined in ``shared.schemas`` -
that module is frozen. The only contract model that is *not* there is
``ParameterSource`` (it exists in ``contracts/openapi.yaml`` but not in
``shared/schemas.py``), so it is defined here with exactly the fields of the
frozen contract.

Nothing in this module may be imported by another agent: it belongs to the API
layer.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from shared.schemas import ParameterValue, SourceRef


class ParameterSource(BaseModel):
    """One value together with the source it was read from (FR-05, FR-12)."""

    model_config = ConfigDict(extra="ignore")

    value: ParameterValue
    source: SourceRef
    page_url: str | None = None
    page_text: str | None = None


class HealthResponse(BaseModel):
    """Body of ``GET /health`` (not part of the frozen contract)."""

    model_config = ConfigDict(extra="ignore")

    status: str = "ok"


class ErrorResponse(BaseModel):
    """The frozen ``Error`` schema: a human readable ``detail`` plus a ``code``."""

    model_config = ConfigDict(extra="ignore")

    detail: str
    code: str | None = None


__all__ = ["ErrorResponse", "HealthResponse", "ParameterSource"]

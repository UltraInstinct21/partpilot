"""Shared fixtures of the data layer tests.

Every test runs on a fresh **in-memory** SQLite database.  The engine keeps a
single connection alive (``StaticPool``) so that the repository sessions all
see the same data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from db.repository import NameMapRepository, SqlAlchemyPartsRepository
from db.session import create_memory_engine, init_db
from shared.schemas import (
    ExtractionMethod,
    Family,
    LifecycleStatus,
    ParameterValue,
    PartRecord,
    SourceRef,
    SourceType,
    ValueStatus,
)


@pytest.fixture
def engine():
    """A fresh in-memory database with the reference schema."""
    memory_engine = create_memory_engine()
    init_db(memory_engine)
    yield memory_engine
    memory_engine.dispose()


@pytest.fixture
def repo(engine) -> SqlAlchemyPartsRepository:
    return SqlAlchemyPartsRepository(engine)


@pytest.fixture
def name_map(engine) -> NameMapRepository:
    return NameMapRepository(engine)


@pytest.fixture
def source() -> SourceRef:
    return SourceRef(
        source_id="pdf-mosfet-irf3205s",
        url="https://example.invalid/datasheets/IRF3205S.pdf",
        type=SourceType.PDF,
        fetched_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        file_hash="deadbeef",
        distributor="digikey",
        page_count=12,
        local_path=None,
        content_type="application/pdf",
        note="synthetic",
    )


def make_value(
    name: str,
    value: float | None = 1.0,
    unit: str | None = None,
    *,
    part_id: str | None = None,
    source_id: str | None = None,
    page: int | None = None,
    method: ExtractionMethod = ExtractionMethod.TIER1,
    confidence: float = 0.85,
    status: ValueStatus = ValueStatus.ACCEPTED,
    condition: dict[str, Any] | None = None,
    param_id: str | None = None,
    value_min: float | None = None,
    value_typ: float | None = None,
    value_max: float | None = None,
    raw_text: str | None = None,
) -> ParameterValue:
    """Build a :class:`ParameterValue` for a test."""
    return ParameterValue(
        param_id=param_id,
        part_id=part_id,
        name=name,
        value=value,
        value_min=value_min,
        value_typ=value_typ,
        value_max=value_max,
        unit=unit,
        condition=condition or {},
        source_id=source_id,
        page=page,
        method=method,
        confidence=confidence,
        status=status,
        raw_text=raw_text,
    )


def make_part(
    part_id: str = "part-1",
    mpn: str = "IRF3205S",
    manufacturer: str = "International Rectifier",
    family: Family = Family.MOSFET,
    package: str | None = "TO-220AB",
    lifecycle_status: LifecycleStatus = LifecycleStatus.ACTIVE,
    parameters: list[ParameterValue] | None = None,
    source_ids: list[str] | None = None,
    description: str | None = "56 V N-channel power MOSFET",
    datasheet_url: str | None = "https://example.invalid/datasheets/IRF3205S.pdf",
) -> PartRecord:
    """Build a :class:`PartRecord` for a test."""
    return PartRecord(
        part_id=part_id,
        mpn=mpn,
        manufacturer=manufacturer,
        family=family,
        package=package,
        lifecycle_status=lifecycle_status,
        datasheet_url=datasheet_url,
        description=description,
        source_ids=source_ids if source_ids is not None else [],
        parameters=parameters or [],
    )

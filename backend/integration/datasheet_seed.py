"""Seed the parts that are read from a datasheet.

The seed fixture holds the values that the distributor APIs returned. Those
have an API source, and an API source has no page to show. The demo needs a
part whose values come from a datasheet page, so this module runs the real
pipeline over the synthetic PDF of each family:

    PDF -> tier 1 -> validation -> database

The synthetic PDF is the one in ``contracts/fixtures/pdfs``. It has a known
table, so the values are known too. In a real run the same code path reads
the downloaded datasheet of the part (WP2).

This module is the **integration** between the extraction, validation and
data layers. It lives outside the three packages on purpose: it is the
composition root for one specific job, and it is the only place that is
allowed to use the three implementations together.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from shared.config import Settings, get_settings
from shared.schemas import (
    ExtractionMethod,
    Family,
    LifecycleStatus,
    ParameterValue,
    PartRecord,
    SourceRef,
    SourceType,
)

logger = logging.getLogger("partpilot.integration")

__all__ = ["DATASHEET_PARTS", "seed_datasheet_parts"]

#: The synthetic datasheet of each family and the part it belongs to.
DATASHEET_PARTS: dict[Family, dict[str, Any]] = {
    Family.MOSFET: {
        "part_id": "mosfet-pmp100n08",
        "mpn": "PMP100N08",
        "manufacturer": "PartPilot Synthetic",
        "package": "TO-220AB",
        "pdf": "synthetic_mosfet.pdf",
        "description": "PartPilot synthetic 100 V N-channel power MOSFET",
    },
    Family.GATE_DRIVER: {
        "part_id": "gate-driver-pgd35",
        "mpn": "PGD35",
        "manufacturer": "PartPilot Synthetic",
        "package": "TO-263-5",
        "pdf": "synthetic_gate_driver.pdf",
        "description": "PartPilot synthetic 35 V high-side gate driver",
    },
}


def seed_datasheet_parts(
    engine: Any,
    settings: Settings | None = None,
) -> list[str]:
    """Extract the synthetic datasheets and store their values.

    Returns the ids of the parts that were written. The function is
    idempotent: running it twice leaves the database in the same state.
    """
    from db.repository import SqlAlchemyPartsRepository
    from extraction.tier1.extractor import PdfTier1Extractor
    from validation.validator import ParameterValidator

    settings = settings or get_settings()
    repository = SqlAlchemyPartsRepository(engine)
    extractor = PdfTier1Extractor()
    validator = ParameterValidator()

    written: list[str] = []
    for family, spec in DATASHEET_PARTS.items():
        pdf_path = settings.fixtures_dir / "pdfs" / spec["pdf"]
        if not pdf_path.exists():
            logger.warning("the synthetic datasheet %s is missing", pdf_path)
            continue

        source_id = f"pdf-{spec['part_id']}"
        result = extractor.extract(str(pdf_path), family, source_id=source_id)
        if result.scanned or not result.values:
            logger.warning("the synthetic datasheet %s gave no values", pdf_path)
            continue

        values = validator.validate_many(result.values)
        for value in values:
            value.part_id = spec["part_id"]
            value.source_id = source_id

        repository.add_source(
            SourceRef(
                source_id=source_id,
                url=f"https://example.invalid/datasheets/{spec['mpn']}.pdf",
                type=SourceType.PDF,
                file_hash=None,
                local_path=str(pdf_path),
                page_count=2,
                content_type="application/pdf",
                note="synthetic datasheet of the demo",
            )
        )
        repository.add_part(
            PartRecord(
                part_id=spec["part_id"],
                mpn=spec["mpn"],
                manufacturer=spec["manufacturer"],
                family=family,
                package=spec["package"],
                lifecycle_status=LifecycleStatus.ACTIVE,
                datasheet_url=f"https://example.invalid/datasheets/{spec['mpn']}.pdf",
                description=spec["description"],
                source_ids=[source_id],
                parameters=values,
            )
        )
        written.append(spec["part_id"])
        logger.info(
            "seeded %s with %s values read from %s",
            spec["part_id"],
            len(values),
            Path(pdf_path).name,
        )
    written.extend(_seed_a_rejected_value(engine, repository, validator, settings))
    return written


def _seed_a_rejected_value(
    engine: Any,
    repository: Any,
    validator: Any,
    settings: Settings,
) -> list[str]:
    """Store a part with a value the validator rejects.

    The demo of the plan (WP9, step 3) shows "a value that the validator
    rejected". A voltage of 5000 V is outside the allowed range of
    ``vds_max``, so the validator rejects it and the part carries a red
    status in the interface.

    The part is clearly named, so nobody mistakes it for real data.
    """
    spec = DATASHEET_PARTS[Family.MOSFET]
    pdf_path = settings.fixtures_dir / "pdfs" / spec["pdf"]
    if not pdf_path.exists():
        return []

    part_id = "mosfet-pmp100n08-out-of-range"
    values = validator.validate_many(
        [
            ParameterValue(
                name="vds_max",
                value=5000.0,
                unit="V",
                condition={},
                page=1,
                method=ExtractionMethod.TIER1,
                raw_text="5000 V",
            )
        ]
    )
    for value in values:
        value.part_id = part_id
        value.source_id = f"pdf-{part_id}"

    repository.add_source(
        SourceRef(
            source_id=f"pdf-{part_id}",
            url=f"https://example.invalid/datasheets/{spec['mpn']}-OUT-OF-RANGE.pdf",
            type=SourceType.PDF,
            local_path=str(pdf_path),
            page_count=2,
            content_type="application/pdf",
            note="demo of a value the validator rejects",
        )
    )
    repository.add_part(
        PartRecord(
            part_id=part_id,
            mpn=f"{spec['mpn']}-OUT-OF-RANGE",
            manufacturer=spec["manufacturer"],
            family=Family.MOSFET,
            package=spec["package"],
            lifecycle_status=LifecycleStatus.ACTIVE,
            datasheet_url=f"https://example.invalid/datasheets/{spec['mpn']}-OUT-OF-RANGE.pdf",
            description="Demo part: one value is outside the allowed range",
            source_ids=[f"pdf-{part_id}"],
            parameters=values,
        )
    )
    logger.info("seeded %s with a value the validator rejects", part_id)
    return [part_id]

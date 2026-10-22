"""Seed list builder (owned by agent A, plan WP1 step 10).

The builder works with and without credentials:

* With credentials it asks DigiKey for the category tree of the family and
  then for the parts of that category. The category search is what finds the
  candidate part numbers.
* Without credentials it falls back to the bundled seed list
  (``contracts/fixtures/seed/parts.json``) so the whole system can be started
  offline.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from collectors.base import CollectorError, MissingCredentialsError
from shared.config import Settings, get_settings
from shared.schemas import (
    ExtractionMethod,
    Family,
    LifecycleStatus,
    ParameterValue,
    PartRecord,
)

logger = logging.getLogger(__name__)

__all__ = [
    "FAMILY_KEYWORDS",
    "bundled_part_records",
    "build_seed_list",
    "load_bundled_parts",
    "load_bundled_seed",
]

#: The keyword that is used for the category search of a family.
FAMILY_KEYWORDS: dict[Family, str] = {
    Family.MOSFET: "MOSFET",
    Family.GATE_DRIVER: "Gate Driver",
}


def _as_family(family: Family | str) -> Family:
    if isinstance(family, Family):
        return family
    return Family(str(family))


def load_bundled_parts(
    family: Family | str | None = None,
    *,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Return the bundled seed parts (optionally filtered by family)."""
    settings = settings or get_settings()
    path = settings.fixtures_dir / "seed" / "parts.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    parts = document.get("parts") or []
    if family is None:
        return [dict(part) for part in parts]
    wanted = _as_family(family).value
    return [dict(part) for part in parts if str(part.get("family")) == wanted]


def load_bundled_seed(
    family: Family | str | None = None,
    *,
    settings: Settings | None = None,
) -> list[str]:
    """Return the bundled manufacturer part numbers.

    Without a family the whole list (30 part numbers) is returned.
    """
    return [str(part.get("mpn")) for part in load_bundled_parts(family, settings=settings)]


def bundled_part_records(
    family: Family | str | None = None,
    *,
    settings: Settings | None = None,
) -> list[PartRecord]:
    """Return the bundled seed parts as :class:`PartRecord` objects."""
    records: list[PartRecord] = []
    for part in load_bundled_parts(family, settings=settings):
        parameters: list[ParameterValue] = []
        for name, raw in (part.get("parameters") or {}).items():
            if not isinstance(raw, dict):
                continue
            parameters.append(
                ParameterValue(
                    part_id=str(part.get("part_id")),
                    name=str(name),
                    value=raw.get("value"),
                    unit=raw.get("unit"),
                    condition=raw.get("condition") or {},
                    source_id=(part.get("source_ids") or [None])[0],
                    page=None,
                    method=ExtractionMethod.API,
                    confidence=0.90,
                )
            )
        lifecycle = str(part.get("lifecycle_status") or "unknown")
        records.append(
            PartRecord(
                part_id=str(part.get("part_id")),
                mpn=str(part.get("mpn")),
                manufacturer=str(part.get("manufacturer")),
                family=_as_family(str(part.get("family"))),
                package=part.get("package"),
                lifecycle_status=(
                    LifecycleStatus(lifecycle)
                    if lifecycle in {item.value for item in LifecycleStatus}
                    else LifecycleStatus.UNKNOWN
                ),
                datasheet_url=part.get("datasheet_url"),
                description=part.get("description"),
                source_ids=list(part.get("source_ids") or []),
                parameters=parameters,
            )
        )
    return records


def build_seed_list(
    family: Family | str,
    limit: int = 25,
    *,
    collector: Any | None = None,
    settings: Settings | None = None,
) -> list[str]:
    """Return up to ``limit`` part numbers of a family.

    ``collector`` is an optional DigiKey collector. When it is missing (or
    fails) the bundled seed list is used, so the function never fails.
    """
    settings = settings or get_settings()
    wanted = _as_family(family)
    limit = max(1, int(limit))
    mpns: list[str] = []

    if collector is not None:
        try:
            mpns = _collect_candidates(collector, wanted, limit)
        except (CollectorError, MissingCredentialsError) as exc:
            logger.warning("the category search failed (%s) - the bundled seed is used", exc)
            mpns = []
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("the category search failed (%s) - the bundled seed is used", exc)
            mpns = []

    if not mpns:
        mpns = load_bundled_seed(wanted, settings=settings)

    seen: set[str] = set()
    result: list[str] = []
    for mpn in mpns:
        if not mpn or mpn in seen:
            continue
        seen.add(mpn)
        result.append(mpn)
        if len(result) >= limit:
            break
    return result


def _collect_candidates(collector: Any, family: Family, limit: int) -> list[str]:
    """Ask the collector for the candidate part numbers of a family."""
    keyword = FAMILY_KEYWORDS[family]
    parts = collector.search_by_keyword(keyword, limit)
    mpns = [str(part.mpn) for part in parts if getattr(part, "mpn", None)]
    if mpns:
        return mpns
    # Fall back to the bundled list when the distributor has no answer.
    return load_bundled_seed(family)

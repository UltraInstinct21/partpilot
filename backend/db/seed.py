"""Seed loader for PartPilot (agent E-data).

Reads ``contracts/fixtures/seed/parts.json`` (30 synthetic parts) and loads
them into the database.  The loader is **idempotent**: running it twice does
not duplicate a single row.

How a seed part becomes a row
-----------------------------
* one ``parts`` row (the id, mpn, manufacturer, family, package, lifecycle
  status, datasheet url and description of the fixture);
* one ``sources`` row per ``source_id`` of the fixture (synthetic URLs, the
  seed data is fake on purpose);
* one ``parameters`` row per parameter of the fixture.  The fixture shape
  ``{"value": ..., "unit": ..., "condition": {...}}`` is turned into a
  :class:`ParameterValue` with a synthetic ``source_id``
  (``api-digikey-<mpn lower>``), ``method=api``, ``confidence=0.9`` and
  ``status=accepted``.  A parameter whose value is ``None`` gets
  ``status=review`` - there is nothing to accept.
* the units are normalised to the canonical unit of the contract (``mohm`` ->
  ``ohm``, ``nC`` -> ``C``, ``pF`` -> ``F``, ``ns`` -> ``s``).

Usage::

    python -m db.seed                 # loads into Settings.database_url
    python -m db.seed --path FILE      # loads another fixture file
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from db.repository import NameMapRepository, SqlAlchemyPartsRepository
from db.session import create_engine_from_settings, init_db
from db.units import canonicalize
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

__all__ = ["DEFAULT_NAME_MAP_PATH", "DEFAULT_SEED_PATH", "load_seed", "main"]

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

#: the frozen fixture with the 30 seed parts.
DEFAULT_SEED_PATH = REPO_ROOT / "contracts" / "fixtures" / "seed" / "parts.json"
#: the alias table of this agent (raw table header -> standard name).
DEFAULT_NAME_MAP_PATH = Path(__file__).resolve().parent / "seed_data" / "name_map.json"

#: confidence of a value that came straight from a distributor API.
API_CONFIDENCE = 0.9


def _synthetic_source_id(mpn: str, source_ids: list[str]) -> str:
    """Return the source id the API values of a part are attributed to."""
    for source_id in source_ids:
        if source_id.startswith("api-digikey"):
            return source_id
    if source_ids:
        return source_ids[0]
    return f"api-digikey-{mpn.lower()}"


def _distributor_of(source_id: str) -> str | None:
    for name in ("digikey", "nexar", "mouser"):
        if name in source_id.lower():
            return name
    return None


def _source_ref(source_id: str, mpn: str) -> SourceRef:
    """Build the synthetic provenance row of a seed source."""
    return SourceRef(
        source_id=source_id,
        url=f"https://example.invalid/sources/{source_id}/{mpn}",
        type=SourceType.API,
        fetched_at=datetime.now(UTC),
        distributor=_distributor_of(source_id),
        content_type="application/json",
        note="synthetic seed source",
    )


def _part_record(payload: dict[str, Any]) -> tuple[PartRecord, list[ParameterValue]]:
    """Turn one fixture part into a record plus its values."""
    part_id = str(payload["part_id"])
    mpn = str(payload["mpn"])
    source_ids = [str(item) for item in payload.get("source_ids") or []]
    value_source_id = _synthetic_source_id(mpn, source_ids)
    part = PartRecord(
        part_id=part_id,
        mpn=mpn,
        manufacturer=str(payload["manufacturer"]),
        family=Family(payload["family"]),
        package=payload.get("package"),
        lifecycle_status=LifecycleStatus(payload.get("lifecycle_status") or "unknown"),
        datasheet_url=payload.get("datasheet_url"),
        description=payload.get("description"),
        source_ids=source_ids,
    )
    values: list[ParameterValue] = []
    for name, spec in (payload.get("parameters") or {}).items():
        spec = spec or {}
        raw_value = spec.get("value")
        unit = spec.get("unit")
        value, canonical_unit = canonicalize(raw_value, unit)
        values.append(
            ParameterValue(
                part_id=part_id,
                name=name,
                value=value,
                unit=canonical_unit,
                condition=dict(spec.get("condition") or {}),
                source_id=value_source_id,
                page=None,
                method=ExtractionMethod.API,
                confidence=API_CONFIDENCE,
                status=ValueStatus.ACCEPTED if raw_value is not None else ValueStatus.REVIEW,
            )
        )
    return part, values


def load_seed(
    engine: Any = None,
    path: str | Path | None = None,
    name_map_path: str | Path | None = None,
) -> dict[str, int]:
    """Load the seed parts into the database and return a small summary.

    The function is idempotent: every row is upserted, so a second run leaves
    the database in exactly the same state.
    """
    if engine is None:
        engine = create_engine_from_settings()
    init_db(engine)

    seed_path = Path(path) if path is not None else DEFAULT_SEED_PATH
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    parts = payload.get("parts") if isinstance(payload, dict) else payload
    if not parts:
        raise ValueError(f"{seed_path} does not contain any part")

    repository = SqlAlchemyPartsRepository(engine)
    name_map = NameMapRepository(engine)

    parts_loaded = 0
    values_loaded = 0
    offers_loaded = 0
    for item in parts:
        part, values = _part_record(item)
        for source_id in part.source_ids:
            repository.add_source(_source_ref(source_id, part.mpn))
        repository.add_part(part.model_copy(update={"parameters": values}))
        for offer in item.get("offers") or []:
            repository.add_offer(part.part_id, offer)
            offers_loaded += 1
        parts_loaded += 1
        values_loaded += len(values)

    mappings_loaded = 0
    map_path = Path(name_map_path) if name_map_path is not None else DEFAULT_NAME_MAP_PATH
    if map_path.exists():
        map_payload = json.loads(map_path.read_text(encoding="utf-8"))
        entries = (
            map_payload.get("name_map") if isinstance(map_payload, dict) else map_payload
        ) or []
        for entry in entries:
            name_map.add(
                raw_name=str(entry["raw_name"]),
                standard_name=str(entry["standard_name"]),
                family=entry.get("family"),
                approved=entry.get("approved", "yes"),
            )
            mappings_loaded += 1

    return {
        "parts": parts_loaded,
        "parameters": values_loaded,
        "offers": offers_loaded,
        "name_map": mappings_loaded,
    }


def main(argv: list[str] | None = None) -> int:
    """Entry point of ``python -m db.seed``."""
    parser = argparse.ArgumentParser(description="Load the PartPilot seed data.")
    parser.add_argument("--path", default=None, help="seed fixture (JSON)")
    parser.add_argument("--name-map", default=None, help="name map fixture (JSON)")
    parser.add_argument("--database-url", default=None, help="override Settings.database_url")
    args = parser.parse_args(argv)

    if args.database_url:
        from db.session import create_engine_for_url

        engine = create_engine_for_url(args.database_url)
    else:
        from shared.config import get_settings

        get_settings().ensure_dirs()
        engine = create_engine_from_settings()

    summary = load_seed(engine, path=args.path, name_map_path=args.name_map)
    print(
        "seeded "
        f"{summary['parts']} parts, "
        f"{summary['parameters']} values, "
        f"{summary['offers']} offers, "
        f"{summary['name_map']} name map entries"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

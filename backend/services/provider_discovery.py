"""Provider-first component discovery.

Provider APIs are queried for every live search/alternative request when their
credentials are configured. Results are deduplicated by MPN, merged across
providers, registered with provenance, and ingested into the repository so the
existing validator, comparison, and source-viewer paths can use them.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from collectors.digikey import DigiKeyCollector
from collectors.mouser import MouserCollector
from collectors.nexar import NexarCollector
from shared.config import Settings
from shared.interfaces import PartsRepository
from shared.schemas import PartRecord, SourceRef, SourceType

logger = logging.getLogger(__name__)


class ProviderDiscoveryService:
    """Search configured distributor APIs and ingest the merged result set."""

    def __init__(self, repository: PartsRepository, settings: Settings) -> None:
        self._repository = repository
        self._collectors = [
            DigiKeyCollector(settings),
            MouserCollector(settings),
            NexarCollector(settings),
        ]

    def discover_and_ingest(self, query: str, limit: int = 12) -> list[PartRecord]:
        if not query.strip():
            return []
        with ThreadPoolExecutor(max_workers=len(self._collectors)) as pool:
            futures = [pool.submit(self._search_one, collector, query, limit) for collector in self._collectors]
            batches = [future.result() for future in futures]

        merged: dict[str, PartRecord] = {}
        for batch in batches:
            for record in batch:
                key = record.mpn.strip().lower()
                if not key:
                    continue
                current = merged.get(key)
                if current is None:
                    merged[key] = record
                    continue
                current.offers.extend(
                    offer for offer in record.offers if offer.distributor not in {item.distributor for item in current.offers}
                )
                if len(record.parameters) > len(current.parameters):
                    current.parameters = record.parameters
                current.source_ids = list(dict.fromkeys([*current.source_ids, *record.source_ids]))

        ingested: list[PartRecord] = []
        for record in list(merged.values())[: max(1, limit)]:
            self._register_sources(record)
            try:
                ingested.append(self._repository.add_part(record))
            except Exception as exc:
                logger.warning("Could not ingest provider result %s: %s", record.mpn, exc)
        return ingested

    @staticmethod
    def _search_one(collector: Any, query: str, limit: int) -> list[PartRecord]:
        try:
            return collector.search_by_keyword(query, limit=limit)
        except Exception as exc:
            logger.info("Provider %s unavailable for %r: %s", collector.name, query, exc)
            return []

    def _register_sources(self, record: PartRecord) -> None:
        for source_id in record.source_ids:
            try:
                self._repository.add_source(
                    SourceRef(
                        source_id=source_id,
                        url=record.datasheet_url or f"https://www.{source_id.split('-')[1]}.com",
                        type=SourceType.API,
                        distributor=source_id.split("-")[1] if "-" in source_id else None,
                        note="Provider-first live discovery result",
                    )
                )
            except Exception as exc:
                logger.debug("Source %s already registered or unavailable: %s", source_id, exc)


__all__ = ["ProviderDiscoveryService"]

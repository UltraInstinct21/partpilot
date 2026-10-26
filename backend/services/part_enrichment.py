"""On-demand part enrichment from distributor APIs and the open web.

When the compare tab (or any part view) requests a part whose details are
thin - fewer than a handful of extracted parameters, an unknown lifecycle, a
missing package or datasheet - this service fills the gaps. It prefers the
authoritative DigiKey Product Information v4 API when credentials are
configured, and always complements the result with bounded web scraping so
missing specifications and multi-distributor offers are recovered too.

Both sources are combined: the API supplies high-confidence structured values,
offers and lifecycle, while scraping catches anything the API omits and adds
regional distributor pricing. The merge never overwrites good existing data -
it only adds what is missing, so provenance and hand-verified values survive.
"""

from __future__ import annotations

import logging

from collectors.digikey import DigiKeyCollector
from services import web_search
from shared.config import Settings
from shared.interfaces import PartsRepository
from shared.schemas import LifecycleStatus, PartRecord, SourceRef, SourceType

logger = logging.getLogger(__name__)

#: A part with fewer accepted values than this is considered "details unavailable".
_MIN_PARAMETERS = 5

#: Manufacturer placeholders produced by scraping that a real API value should replace.
_SCRAPED_PLACEHOLDERS = frozenset({"", "unknown (scraped)", "unknown", "unknown (scraped web)"})


def needs_enrichment(part: PartRecord) -> bool:
    """Return True when a part is missing enough detail to be worth enriching."""
    if len(part.parameters) < _MIN_PARAMETERS:
        return True
    if part.lifecycle_status == LifecycleStatus.UNKNOWN:
        return True
    if not part.package:
        return True
    if not part.datasheet_url or "invalid" in (part.datasheet_url or ""):
        return True
    return False


class PartEnrichmentService:
    """Fill in the missing details of a part from DigiKey and the web."""

    def __init__(self, repository: PartsRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    # ----------------------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------------------
    def enrich(self, part_id: str) -> PartRecord | None:
        """Return the enriched part, or None when it cannot be found/enriched."""
        part = self._repository.get_part(part_id)
        if part is None:
            return None
        if not needs_enrichment(part):
            return part

        enriched = False

        # 1. DigiKey API first - authoritative structured values, offers and lifecycle.
        api_record = self._fetch_from_digikey(part.mpn)
        if api_record is not None:
            part = self._merge_api_record(part, api_record)
            enriched = True

        # 2. Web scraping - recover remaining specs, a real datasheet and more offers.
        try:
            web = web_search.WebDiscoveryService(self._settings.searxng_url, repository=self._repository)
            scraped = web.deep_scrape_part(part_id)
            if scraped is not None:
                part = scraped
                enriched = True
        except Exception as exc:
            logger.debug("Web scrape enrichment skipped for %s: %s", part_id, exc)

        if not enriched:
            return part

        # 3. Persist the merged record so subsequent requests hit the cache.
        try:
            return self._repository.add_part(part)
        except Exception:
            return self._repository.get_part(part_id) or part

    # ----------------------------------------------------------------------------------
    # DigiKey
    # ----------------------------------------------------------------------------------
    def _fetch_from_digikey(self, mpn: str) -> PartRecord | None:
        """Query the DigiKey v4 API for ``mpn`` and normalise it, or None."""
        if not (self._settings.digikey_client_id and self._settings.digikey_client_secret.get_secret_value()):
            logger.debug("DigiKey credentials are not configured - API enrichment skipped")
            return None
        if not mpn:
            return None
        try:
            collector = DigiKeyCollector(self._settings)
            record = collector.search_by_mpn(mpn)  # sync facade (runs the async client)
            return record
        except Exception as exc:
            logger.info("DigiKey API unavailable for %s: %s", mpn, exc)
            return None

    # ----------------------------------------------------------------------------------
    # Merge
    # ----------------------------------------------------------------------------------
    def _merge_api_record(self, part: PartRecord, api: PartRecord) -> PartRecord:
        """Fold the authoritative DigiKey record into ``part`` without losing data."""
        # Scalar fields - only fill blanks or replace scraping placeholders.
        if not part.package and api.package:
            part.package = api.package
        if part.lifecycle_status == LifecycleStatus.UNKNOWN and api.lifecycle_status != LifecycleStatus.UNKNOWN:
            part.lifecycle_status = api.lifecycle_status
        if not part.datasheet_url and api.datasheet_url:
            part.datasheet_url = api.datasheet_url
        if not part.description and api.description:
            part.description = api.description
        if part.manufacturer.strip().lower() in _SCRAPED_PLACEHOLDERS and api.manufacturer:
            part.manufacturer = api.manufacturer

        # Parameters - add any the API knows that we do not, keeping API provenance.
        existing_names = {p.name for p in part.parameters}
        for param in api.parameters:
            if param.name in existing_names:
                continue
            param.part_id = part.part_id
            part.parameters.append(param)
            existing_names.add(param.name)

        # Offers - add the DigiKey offer when we have none from it yet.
        distributors = {o.distributor.lower() for o in part.offers}
        for offer in api.offers:
            if offer.distributor.lower() in distributors:
                continue
            offer.part_id = part.part_id
            part.offers.append(offer)
            distributors.add(offer.distributor.lower())

        # Provenance - register the API sources so the source viewer can resolve them.
        for source_id in api.source_ids:
            if source_id in part.source_ids:
                continue
            part.source_ids.append(source_id)
            self._register_api_source(source_id, api.datasheet_url)

        return part

    def _register_api_source(self, source_id: str, datasheet_url: str | None) -> None:
        """Persist a provenance row for a distributor API source, ignoring duplicates."""
        distributor = source_id.split("-")[1] if source_id.count("-") >= 2 else "digikey"
        try:
            self._repository.add_source(
                SourceRef(
                    source_id=source_id,
                    url=datasheet_url or f"https://www.{distributor}.com",
                    type=SourceType.API,
                    distributor=distributor,
                    note="On-demand distributor API enrichment (compare/details fallback)",
                )
            )
        except Exception as exc:
            logger.debug("Source %s already registered or unavailable: %s", source_id, exc)


__all__ = ["PartEnrichmentService", "needs_enrichment"]

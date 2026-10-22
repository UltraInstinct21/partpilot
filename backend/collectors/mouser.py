"""Mouser Search API client (owned by agent A).

Endpoints (verified in ``docs/CONTRACTS.md``):

* ``POST https://api.mouser.com/api/v1/search/keyword?apiKey=<key>``
  body ``{"SearchByKeywordRequest": {"keyword", "records", "startingRecord",
  "searchOptions"}}``
* ``POST https://api.mouser.com/api/v1/search/partnumber?apiKey=<key>``
  body ``{"SearchByPartRequest": {"mouserPartNumber": "A|B",
  "partSearchOptions": "Exact"}}`` - up to 10 part numbers, pipe separated.
* v2: ``/api/v2/search/keywordandmanufacturer``,
  ``/api/v2/search/partnumberandmanufacturer`` and
  ``/api/v2/search/manufacturerlist``.

The API key travels in the query string. It is never written to the cache and
never logged - the ``httpx`` log records are filtered so the key is redacted.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from collectors.base import (
    CollectorError,
    DiskCache,
    MissingCredentialsError,
    RateLimiter,
    RetryPolicy,
    cache_key,
    http_client,
    request_with_retry,
    run_sync,
)
from collectors.params import (
    canonical_unit,
    infer_family,
    parse_condition,
    parse_value_with_unit,
    resolve_parameter_name,
    slugify,
)
from shared.config import Settings, get_settings
from shared.schemas import (
    ExtractionMethod,
    Family,
    LifecycleStatus,
    Offer,
    ParameterValue,
    PartRecord,
)

logger = logging.getLogger(__name__)

__all__ = ["MouserCollector", "parse_bool"]

API_CONFIDENCE = 0.90

#: Mouser accepts at most 10 part numbers per call.
MAX_PART_NUMBERS = 10

#: Mouser returns at most 50 records per call.
MAX_RECORDS = 50


class _ApiKeyRedactingFilter(logging.Filter):
    """Remove ``apiKey=...`` from every log record of the httpx loggers."""

    _pattern = re.compile(r"apiKey=[^&\s\"']+")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "apiKey=" in message:
            record.msg = self._pattern.sub("apiKey=***", message)
            record.args = ()
        return True


def _install_redacting_filter() -> None:
    """Attach the redaction filter once to the httpx loggers."""
    for name in ("httpx", "httpcore"):
        target = logging.getLogger(name)
        if not any(isinstance(f, _ApiKeyRedactingFilter) for f in target.filters):
            target.addFilter(_ApiKeyRedactingFilter())


_install_redacting_filter()


def parse_bool(value: Any) -> bool | None:
    """Parse the many ways an API reports a boolean.

    Mouser sends ``IsDiscontinued`` as the *string* ``"true"`` / ``"false"``.
    ``None`` is returned when the value says nothing about the flag.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1"}:
        return True
    if text in {"false", "no", "n", "0"}:
        return False
    return None


class MouserCollector:
    """Collect part data from the Mouser Search API."""

    name = "mouser"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        cache: DiskCache | None = None,
        limiter: RateLimiter | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self.cache = cache or DiskCache(self.settings.raw_dir, self.name)
        self.limiter = limiter or RateLimiter(
            self.name,
            self.settings.mouser_rate_limit_per_minute,
            self.settings.mouser_rate_limit_per_day,
        )
        self.retry = retry or RetryPolicy.from_settings(self.settings)
        self.base_url = self.settings.mouser_base_url.rstrip("/")
        self.v2_base_url = re.sub(r"/api/v\d+$", "/api/v2", self.base_url)

    # ----------------------------------------------------------------------------------
    # Authentication
    # ----------------------------------------------------------------------------------
    def _require_credentials(self) -> None:
        if not self.settings.mouser_api_key.get_secret_value():
            raise MissingCredentialsError(
                "Mouser credentials are missing (PARTPILOT_MOUSER_API_KEY)"
            )

    # ----------------------------------------------------------------------------------
    # Low level request handling
    # ----------------------------------------------------------------------------------
    async def _post(
        self,
        path: str,
        body: dict[str, Any],
        *,
        base_url: str | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Send one POST request. A cache hit makes no network call at all."""
        self._require_credentials()
        url = f"{(base_url or self.base_url).rstrip('/')}{path}"
        # The cache key never contains the API key - only the path and the body.
        key = cache_key(self.name, "POST", path, body)
        if use_cache:
            cached = self.cache.get(key)
            if cached is not None:
                logger.debug("cache hit for the Mouser request %s", path)
                return cached
        params = {"apiKey": self.settings.mouser_api_key.get_secret_value()}
        self.limiter.acquire()
        async with http_client(self.settings, self._client) as client:
            response = await request_with_retry(
                self.retry,
                client,
                "POST",
                url,
                json=body,
                params=params,
                headers={"Accept": "application/json"},
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        errors = payload.get("Errors") or []
        if errors:
            raise CollectorError(f"Mouser returned errors: {errors}")
        if use_cache:
            self.cache.put(key, payload)
        return payload

    # ----------------------------------------------------------------------------------
    # Endpoints
    # ----------------------------------------------------------------------------------
    async def search_part_number(self, mpns: list[str]) -> dict[str, Any]:
        """Search up to ten part numbers (exact match)."""
        numbers = [m for m in mpns if m][:MAX_PART_NUMBERS]
        body = {
            "SearchByPartRequest": {
                "mouserPartNumber": "|".join(numbers),
                "partSearchOptions": "Exact",
            }
        }
        return await self._post("/search/partnumber", body)

    async def search_keyword(self, keyword: str, limit: int = 25) -> dict[str, Any]:
        """Search free text."""
        body = {
            "SearchByKeywordRequest": {
                "keyword": keyword,
                "records": max(1, min(int(limit), MAX_RECORDS)),
                "startingRecord": 0,
                "searchOptions": "None",
            }
        }
        return await self._post("/search/keyword", body)

    async def search_part_number_and_manufacturer(
        self, mpns: list[str], manufacturer: str
    ) -> dict[str, Any]:
        """v2 search that also filters by the manufacturer."""
        numbers = [m for m in mpns if m][:MAX_PART_NUMBERS]
        body = {
            "SearchByPartAndManufacturerRequest": {
                "mouserPartNumber": "|".join(numbers),
                "manufacturer": manufacturer,
                "partSearchOptions": "Exact",
            }
        }
        return await self._post(
            "/search/partnumberandmanufacturer", body, base_url=self.v2_base_url
        )

    async def manufacturer_list(self) -> dict[str, Any]:
        """v2 manufacturer list."""
        return await self._post("/search/manufacturerlist", {}, base_url=self.v2_base_url)

    # ----------------------------------------------------------------------------------
    # Normalisation
    # ----------------------------------------------------------------------------------
    @staticmethod
    def _parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
        results = payload.get("SearchResults") or {}
        parts = results.get("Parts") if isinstance(results, dict) else None
        return [p for p in (parts or []) if isinstance(p, dict)]

    def normalize_part(self, part: dict[str, Any]) -> PartRecord:
        """Turn one Mouser part into a :class:`PartRecord`."""
        mpn = str(part.get("ManufacturerPartNumber") or "").strip()
        manufacturer = str(part.get("Manufacturer") or "").strip()
        description = part.get("Description")
        category = part.get("Category")
        family = self._family(category, description)
        slug = slugify(mpn)
        source_id = f"api-{self.name}-{slug}"
        part_id = f"{family.value.replace('_', '-')}-{slug}"

        parameters = self._parameters(part, part_id, source_id)
        package = next(
            (p.value_text for p in parameters if p.name == "package" and p.value_text), None
        )
        discontinued = parse_bool(part.get("IsDiscontinued"))
        record = PartRecord(
            part_id=part_id,
            mpn=mpn,
            manufacturer=manufacturer,
            family=family,
            package=package,
            lifecycle_status=self._lifecycle(part, discontinued),
            datasheet_url=part.get("DataSheetUrl"),
            description=str(description) if description else None,
            source_ids=[source_id],
            parameters=parameters,
            updated_at=datetime.now(UTC),
        )
        record.offers = self._offers(part, part_id, discontinued)
        return record

    def _parameters(
        self,
        part: dict[str, Any],
        part_id: str,
        source_id: str,
    ) -> list[ParameterValue]:
        """Parse ``ProductAttributes`` into parameter values."""
        values: list[ParameterValue] = []
        for attribute in part.get("ProductAttributes") or []:
            if not isinstance(attribute, dict):
                continue
            label = attribute.get("AttributeName")
            standard = resolve_parameter_name(label)
            if standard is None:
                logger.debug("unknown Mouser attribute %r - skipped", label)
                continue
            raw_value = attribute.get("AttributeValue")
            number, unit = parse_value_with_unit(raw_value)
            if number is None and standard != "package":
                continue
            values.append(
                ParameterValue(
                    part_id=part_id,
                    name=standard,
                    value=number,
                    unit=canonical_unit(unit) or unit,
                    condition=parse_condition(label),
                    source_id=source_id,
                    page=None,
                    method=ExtractionMethod.API,
                    confidence=API_CONFIDENCE,
                    raw_text=str(raw_value) if raw_value is not None else None,
                    value_text=str(raw_value) if raw_value is not None else None,
                )
            )
        return values

    @staticmethod
    def _lifecycle(part: dict[str, Any], discontinued: bool | None) -> LifecycleStatus:
        if discontinued:
            return LifecycleStatus.OBSOLETE
        status = str(part.get("LifecycleStatus") or "").strip().lower()
        if status in {"new product", "active", "new"}:
            return LifecycleStatus.ACTIVE
        if status in {"not recommended for new designs", "nrnd"}:
            return LifecycleStatus.NRND
        if status in {"obsolete", "end of life", "discontinued", "eol"}:
            return LifecycleStatus.OBSOLETE
        return LifecycleStatus.UNKNOWN

    @staticmethod
    def _family(category: str | None, description: str | None) -> Family:
        guessed = infer_family(category, description)
        if guessed:
            return Family(guessed)
        logger.warning("cannot determine the family of %s - assuming mosfet", description)
        return Family.MOSFET

    def _offers(
        self,
        part: dict[str, Any],
        part_id: str,
        discontinued: bool | None,
    ) -> list[Offer]:
        breaks = []
        for price in part.get("PriceBreaks") or []:
            if not isinstance(price, dict):
                continue
            number, unit = parse_value_with_unit(price.get("Price"))
            breaks.append(
                {
                    "quantity": price.get("Quantity"),
                    "unit_price": number,
                    "currency": price.get("Currency", "USD"),
                }
            )
        unit_price = next((b["unit_price"] for b in breaks if b["unit_price"] is not None), None)
        stock: int | None = None
        stock_value = part.get("AvailabilityInStock")
        try:
            stock = int(str(stock_value).replace(",", "").strip())
        except (TypeError, ValueError):
            stock = None
        lead_time = self._lead_time(part.get("LeadTime"))
        return [
            Offer(
                part_id=part_id,
                distributor=self.name,
                sku=part.get("MouserPartNumber"),
                stock=stock,
                unit_price=float(unit_price) if unit_price is not None else None,
                currency=str(breaks[0]["currency"]) if breaks else "USD",
                price_breaks=breaks,
                lead_time_days=lead_time,
                url=part.get("ProductDetailUrl"),
                fetched_at=datetime.now(UTC),
            )
        ]

    @staticmethod
    def _lead_time(text: Any) -> int | None:
        if text is None:
            return None
        match = re.search(r"(\d+)", str(text))
        return int(match.group(1)) if match else None

    # ----------------------------------------------------------------------------------
    # Collector protocol
    # ----------------------------------------------------------------------------------
    async def search_by_mpn_async(self, mpn: str) -> PartRecord | None:
        """Return the normalised part for ``mpn`` or ``None``."""
        self._require_credentials()
        try:
            payload = await self.search_part_number([mpn])
        except MissingCredentialsError:
            raise
        except (CollectorError, httpx.TransportError) as exc:
            logger.warning("Mouser has no part %s (%s)", mpn, exc)
            return None
        for part in self._parts(payload):
            candidate = str(part.get("ManufacturerPartNumber") or "").strip()
            if candidate.lower() == mpn.strip().lower():
                return self.normalize_part(part)
        parts = self._parts(payload)
        if parts:
            return self.normalize_part(parts[0])
        logger.warning("Mouser returned no part for %s", mpn)
        return None

    async def search_by_keyword_async(self, keyword: str, limit: int = 25) -> list[PartRecord]:
        """Return the normalised parts of a keyword search."""
        self._require_credentials()
        payload = await self.search_keyword(keyword, limit)
        records = [self.normalize_part(part) for part in self._parts(payload)]
        return records[:limit]

    async def get_offers_async(self, mpn: str) -> list[dict[str, Any]]:
        """Return the raw distributor offers of ``mpn``."""
        self._require_credentials()
        payload = await self.search_part_number([mpn])
        parts = self._parts(payload)
        matching = [
            part
            for part in parts
            if str(part.get("ManufacturerPartNumber") or "").strip().lower() == mpn.strip().lower()
        ]
        offers: list[dict[str, Any]] = []
        for part in matching or parts:
            discontinued = parse_bool(part.get("IsDiscontinued"))
            for offer in self._offers(part, "", discontinued):
                offers.append(
                    {
                        "distributor": offer.distributor,
                        "mpn": mpn,
                        "sku": offer.sku,
                        "stock": offer.stock,
                        "unit_price": offer.unit_price,
                        "currency": offer.currency,
                        "price_breaks": offer.price_breaks,
                        "lead_time_days": offer.lead_time_days,
                        "url": offer.url,
                        "is_discontinued": discontinued,
                        "fetched_at": offer.fetched_at.isoformat() if offer.fetched_at else None,
                    }
                )
        return offers

    def search_by_mpn(self, mpn: str) -> PartRecord | None:
        """Return the normalised part for ``mpn`` or ``None`` when not found."""
        return run_sync(self.search_by_mpn_async(mpn))

    def search_by_keyword(self, keyword: str, limit: int = 25) -> list[PartRecord]:
        """Return normalised parts matching a free-text keyword."""
        return run_sync(self.search_by_keyword_async(keyword, limit))

    def get_offers(self, mpn: str) -> list[dict[str, Any]]:
        """Return raw distributor offers for ``mpn`` (price breaks, stock)."""
        return run_sync(self.get_offers_async(mpn))

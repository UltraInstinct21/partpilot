"""DigiKey Product Information v4 client (owned by agent A).

Endpoints (verified in ``docs/CONTRACTS.md``):

* ``POST /v1/oauth2/token`` - form encoded ``client_id``, ``client_secret``,
  ``grant_type=client_credentials``. The token lives 10 minutes, so it is
  refreshed 60 seconds before it expires.
* ``GET  /products/v4/search/{productNumber}/productdetails``
* ``GET  /products/v4/search/{productNumber}/pricing``
* ``GET  /products/v4/search/{productNumber}/media``
* ``GET  /products/v4/search/{productNumber}/substitutions``
* ``POST /products/v4/search/keyword``
* ``GET  /products/v4/search/categories``

Every call sends ``X-DIGIKEY-Client-Id``, ``Authorization: Bearer <token>``,
``X-DIGIKEY-Locale-Site``, ``X-DIGIKEY-Locale-Language`` and
``X-DIGIKEY-Locale-Currency``. Every raw response is cached on disk with the
date, so the same part is never requested twice (DigiKey allows 1000
requests/day).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from collectors.base import (
    CollectorError,
    DiskCache,
    MissingCredentialsError,
    RateLimiter,
    RetryPolicy,
    TokenCache,
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
    SourceType,
)

logger = logging.getLogger(__name__)

__all__ = ["DigiKeyCollector"]

#: Confidence of a value that was read from an official API (contract section
#: "Confidence model": base 0.90 for the method ``api``).
API_CONFIDENCE = 0.90


class DigiKeyCollector:
    """Collect part data from the DigiKey v4 API."""

    name = "digikey"

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
            self.settings.digikey_rate_limit_per_minute,
            self.settings.digikey_rate_limit_per_day,
        )
        self.retry = retry or RetryPolicy.from_settings(self.settings)
        self._token = TokenCache(refresh_margin=60.0)

    # ----------------------------------------------------------------------------------
    # Authentication
    # ----------------------------------------------------------------------------------
    def _require_credentials(self) -> None:
        if (
            not self.settings.digikey_client_id
            or not self.settings.digikey_client_secret.get_secret_value()
        ):
            raise MissingCredentialsError(
                "DigiKey credentials are missing "
                "(PARTPILOT_DIGIKEY_CLIENT_ID / PARTPILOT_DIGIKEY_CLIENT_SECRET)"
            )

    async def access_token(self) -> str:
        """Return a valid access token, refreshing it when it is about to expire."""
        cached = self._token.token
        if cached:
            return cached
        self._require_credentials()
        url = f"{self.settings.digikey_base_url.rstrip('/')}/v1/oauth2/token"
        payload = {
            "client_id": self.settings.digikey_client_id,
            "client_secret": self.settings.digikey_client_secret.get_secret_value(),
            "grant_type": "client_credentials",
        }
        async with http_client(self.settings, self._client) as client:
            response = await request_with_retry(
                self.retry,
                client,
                "POST",
                url,
                data=payload,
                headers={"Accept": "application/json"},
            )
        body = response.json()
        token = body.get("access_token")
        if not token:
            raise CollectorError("DigiKey did not return an access token")
        self._token.set(token, float(body.get("expires_in", 600)))
        return str(token)

    def _api_headers(self, token: str) -> dict[str, str]:
        return {
            "X-DIGIKEY-Client-Id": self.settings.digikey_client_id,
            "Authorization": f"Bearer {token}",
            "X-DIGIKEY-Locale-Site": self.settings.digikey_locale_site,
            "X-DIGIKEY-Locale-Language": self.settings.digikey_locale_language,
            "X-DIGIKEY-Locale-Currency": self.settings.digikey_locale_currency,
            "Accept": "application/json",
        }

    # ----------------------------------------------------------------------------------
    # Low level request handling
    # ----------------------------------------------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> Any:
        """Send one request. A cache hit makes no network call at all."""
        url = f"{self.settings.digikey_base_url.rstrip('/')}{path}"
        key = cache_key(self.name, method, url, params or {}, body or {})
        if use_cache:
            cached = self.cache.get(key)
            if cached is not None:
                logger.debug("cache hit for %s %s", method, url)
                return cached
        token = await self.access_token()
        headers = self._api_headers(token)
        self.limiter.acquire()

        async with http_client(self.settings, self._client) as client:
            response = await request_with_retry(
                self.retry,
                client,
                method,
                url,
                params=params,
                json=body,
                headers=headers,
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {"_raw": response.text}
        if use_cache:
            self.cache.put(key, payload)
        return payload

    # ----------------------------------------------------------------------------------
    # Endpoints
    # ----------------------------------------------------------------------------------
    async def fetch_product_details(self, mpn: str) -> dict[str, Any] | None:
        """Return the raw product details document of ``mpn``."""
        path = f"/products/v4/search/{mpn}/productdetails"
        payload = await self._request("GET", path)
        product = payload.get("Product") if isinstance(payload, dict) else None
        return product if isinstance(product, dict) else None

    async def fetch_pricing(self, mpn: str) -> dict[str, Any]:
        """Return the raw pricing document of ``mpn``."""
        path = f"/products/v4/search/{mpn}/pricing"
        payload = await self._request("GET", path)
        return payload if isinstance(payload, dict) else {}

    async def fetch_media(self, mpn: str) -> dict[str, Any]:
        """Return the raw media document of ``mpn``."""
        path = f"/products/v4/search/{mpn}/media"
        payload = await self._request("GET", path)
        return payload if isinstance(payload, dict) else {}

    async def fetch_substitutions(self, mpn: str) -> dict[str, Any]:
        """Return the raw substitutions document of ``mpn``."""
        path = f"/products/v4/search/{mpn}/substitutions"
        payload = await self._request("GET", path)
        return payload if isinstance(payload, dict) else {}

    async def search_keyword(self, keyword: str, limit: int = 25) -> dict[str, Any]:
        """Run a keyword search and return the raw document."""
        body = {
            "Keywords": keyword,
            "Limit": max(1, min(int(limit), 100)),
            "Offset": 0,
            "ProductStatus": "Active",
        }
        payload = await self._request("POST", "/products/v4/search/keyword", body=body)
        return payload if isinstance(payload, dict) else {}

    async def search_categories(self, keyword: str, limit: int = 25) -> dict[str, Any]:
        """Search the category tree and return the raw document."""
        params = {"keyword": keyword, "limit": max(1, min(int(limit), 100))}
        payload = await self._request("GET", "/products/v4/search/categories", params=params)
        return payload if isinstance(payload, dict) else {}

    # ----------------------------------------------------------------------------------
    # Normalisation
    # ----------------------------------------------------------------------------------
    def normalize_product(self, product: dict[str, Any]) -> PartRecord:
        """Turn one DigiKey product document into a :class:`PartRecord`."""
        mpn = str(product.get("ManufacturerProductNumber") or "").strip()
        manufacturer = str((product.get("Manufacturer") or {}).get("Name") or "").strip()
        description = product.get("Description")
        category = (product.get("Category") or {}).get("Name")
        family = self._family(product, category, description)
        slug = slugify(mpn)
        source_id = f"api-{self.name}-{slug}"
        part_id = f"{family.value.replace('_', '-')}-{slug}"

        parameters: list[ParameterValue] = []
        package: str | None = None
        raw_parameters = ((product.get("Parameters") or {}).get("Parameter")) or []
        for entry in raw_parameters:
            if not isinstance(entry, dict):
                continue
            label = entry.get("Text")
            standard = resolve_parameter_name(label)
            if standard is None:
                logger.debug("unknown DigiKey parameter label %r - skipped", label)
                continue
            raw_value = entry.get("Value")
            number, unit = parse_value_with_unit(raw_value)
            condition = parse_condition(label)
            value = ParameterValue(
                part_id=part_id,
                name=standard,
                value=number,
                unit=canonical_unit(unit) or unit,
                condition=condition,
                source_id=source_id,
                page=None,
                method=ExtractionMethod.API,
                confidence=API_CONFIDENCE,
                raw_text=str(raw_value) if raw_value is not None else None,
                value_text=str(raw_value) if raw_value is not None else None,
            )
            if standard == "package":
                package = str(raw_value) if raw_value is not None else None
            if number is None and standard != "package":
                # Keep the text, but do not invent a number.
                continue
            parameters.append(value)

        lifecycle = self._lifecycle(product)
        record = PartRecord(
            part_id=part_id,
            mpn=mpn,
            manufacturer=manufacturer,
            family=family,
            package=package,
            lifecycle_status=lifecycle,
            datasheet_url=product.get("DatasheetUrl"),
            description=str(description) if description else None,
            source_ids=[source_id],
            parameters=parameters,
            updated_at=datetime.now(UTC),
        )
        record.offers = self._offers_from_product(product, part_id)
        return record

    def _family(
        self,
        product: dict[str, Any],
        category: str | None,
        description: str | None,
    ) -> Family:
        raw = str(product.get("Family") or "").strip().lower()
        if raw in {f.value for f in Family}:
            return Family(raw)
        guessed = infer_family(category, description, product.get("ProductUrl"))
        if guessed:
            return Family(guessed)
        logger.warning("cannot determine the family of %s - assuming mosfet", product)
        return Family.MOSFET

    @staticmethod
    def _lifecycle(product: dict[str, Any]) -> LifecycleStatus:
        status = str((product.get("Status") or {}).get("LifecycleStatus") or "").strip().lower()
        if status in {"active"}:
            return LifecycleStatus.ACTIVE
        if status in {"nrnd", "not recommended for new designs"}:
            return LifecycleStatus.NRND
        if status in {"obsolete", "discontinued"}:
            return LifecycleStatus.OBSOLETE
        return LifecycleStatus.UNKNOWN

    def _offers_from_product(self, product: dict[str, Any], part_id: str) -> list[Offer]:
        offers: list[Offer] = []
        for variation in product.get("ProductVariations") or []:
            if not isinstance(variation, dict):
                continue
            breaks = []
            for price in variation.get("StandardPricing") or []:
                if not isinstance(price, dict):
                    continue
                breaks.append(
                    {
                        "quantity": price.get("BreakQuantity"),
                        "unit_price": price.get("UnitPrice"),
                        "total_price": price.get("TotalPrice"),
                    }
                )
            unit_price = breaks[0]["unit_price"] if breaks else product.get("UnitPrice")
            offers.append(
                Offer(
                    part_id=part_id,
                    distributor=self.name,
                    sku=variation.get("DigiKeyProductNumber"),
                    stock=variation.get("QuantityAvailableforPackageType")
                    or product.get("QuantityAvailable"),
                    unit_price=float(unit_price) if isinstance(unit_price, (int, float)) else None,
                    currency=self.settings.digikey_locale_currency,
                    price_breaks=breaks,
                    url=product.get("ProductUrl"),
                    fetched_at=datetime.now(UTC),
                )
            )
        return offers

    # ----------------------------------------------------------------------------------
    # Collector protocol
    # ----------------------------------------------------------------------------------
    async def search_by_mpn_async(self, mpn: str) -> PartRecord | None:
        """Return the normalised part for ``mpn`` or ``None``."""
        self._require_credentials()
        try:
            product = await self.fetch_product_details(mpn)
        except MissingCredentialsError:
            raise
        except (CollectorError, httpx.TransportError) as exc:
            logger.warning("DigiKey has no product %s (%s)", mpn, exc)
            return None
        if not product:
            logger.warning("DigiKey returned no product for %s", mpn)
            return None
        return self.normalize_product(product)

    async def search_by_keyword_async(self, keyword: str, limit: int = 25) -> list[PartRecord]:
        """Return the normalised parts of a keyword search."""
        self._require_credentials()
        payload = await self.search_keyword(keyword, limit)
        records: list[PartRecord] = []
        for product in payload.get("Products") or []:
            if not isinstance(product, dict):
                continue
            records.append(self.normalize_product(product))
            if len(records) >= limit:
                break
        return records

    async def get_offers_async(self, mpn: str) -> list[dict[str, Any]]:
        """Return the raw distributor offers of ``mpn``."""
        self._require_credentials()
        payload = await self.fetch_pricing(mpn)
        return self.parse_offers(payload, mpn)

    def parse_offers(self, payload: dict[str, Any], mpn: str) -> list[dict[str, Any]]:
        """Turn a raw pricing document into offer dictionaries."""
        breaks: list[dict[str, Any]] = []
        variations = payload.get("ProductVariations")
        if isinstance(variations, list):
            for variation in variations:
                if not isinstance(variation, dict):
                    continue
                for price in variation.get("StandardPricing") or []:
                    if isinstance(price, dict):
                        breaks.append(
                            {
                                "quantity": price.get("BreakQuantity"),
                                "unit_price": price.get("UnitPrice"),
                            }
                        )
        for price in payload.get("ProductPricing") or payload.get("Pricing") or []:
            if isinstance(price, dict):
                breaks.append(
                    {
                        "quantity": price.get("BreakQuantity"),
                        "unit_price": price.get("UnitPrice"),
                    }
                )
        if not breaks:
            return []
        first = next((b["unit_price"] for b in breaks if b.get("unit_price") is not None), None)
        return [
            {
                "distributor": self.name,
                "mpn": mpn,
                "sku": None,
                "stock": payload.get("QuantityAvailable"),
                "unit_price": first,
                "currency": self.settings.digikey_locale_currency,
                "price_breaks": breaks,
                "url": None,
                "fetched_at": datetime.now(UTC).isoformat(),
                "source_type": SourceType.API.value,
            }
        ]

    def search_by_mpn(self, mpn: str) -> PartRecord | None:
        """Return the normalised part for ``mpn`` or ``None`` when not found."""
        return run_sync(self.search_by_mpn_async(mpn))

    def search_by_keyword(self, keyword: str, limit: int = 25) -> list[PartRecord]:
        """Return normalised parts matching a free-text keyword."""
        return run_sync(self.search_by_keyword_async(keyword, limit))

    def get_offers(self, mpn: str) -> list[dict[str, Any]]:
        """Return raw distributor offers for ``mpn`` (price breaks, stock)."""
        return run_sync(self.get_offers_async(mpn))

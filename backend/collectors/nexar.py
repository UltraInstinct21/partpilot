"""Nexar (Octopart supply data) GraphQL client (owned by agent A).

* Token: ``POST https://identity.nexar.com/connect/token`` with
  ``grant_type=client_credentials``, ``client_id``, ``client_secret`` and
  ``scope=supply.domain``. The token lives 24 hours.
* GraphQL: ``POST https://api.nexar.com/graphql`` with
  ``Authorization: Bearer <token>`` and a body of ``{"query": ..., "variables": ...}``.

The query names are camelCase and prefixed with ``sup``: ``supSearchMpn``,
``supSearch``, ``supMultiMatch``, ``supParts``, ``supCategories`` and
``supManufacturers``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from collectors.base import (
    CollectorError,
    DiskCache,
    HttpStatusError,
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
)

logger = logging.getLogger(__name__)

__all__ = ["NexarCollector"]

API_CONFIDENCE = 0.90

_PART_FIELDS = """
      id
      mpn
      name
      description
      totalAvail
      manufacturer { id name }
      category { id name }
      lifecycle { status }
      specs {
        attribute { id name shortname }
        value
        displayValue
        unitsName
        unitsSymbol
      }
      sellers {
        company { id name isVerified }
        isAuthorized
        offers {
          id
          sku
          inventoryLevel
          moq
          prices { quantity convertedPrice convertedCurrency }
        }
      }
"""

QUERY_SEARCH_MPN = f"""
query supSearchMpn($q: String!, $limit: Int!) {{
  supSearchMpn(q: $q, limit: $limit) {{
    hits
    results {{
      part {{{_PART_FIELDS}
      }}
    }}
  }}
}}
"""

QUERY_SEARCH = f"""
query supSearch($q: String!, $filters: [String], $sort: [String], $start: Int!) {{
  supSearch(q: $q, filters: $filters, sort: $sort, start: $start) {{
    hits
    results {{
      part {{{_PART_FIELDS}
      }}
    }}
  }}
}}
"""

QUERY_MULTI_MATCH = f"""
query supMultiMatch($queries: [String!]!) {{
  supMultiMatch(queries: $queries) {{
    hits
    results {{
      part {{{_PART_FIELDS}
      }}
    }}
  }}
}}
"""

QUERY_PARTS = f"""
query supParts($ids: [String!]!) {{
  supParts(ids: $ids) {{
    hits
    results {{
      part {{{_PART_FIELDS}
      }}
    }}
  }}
}}
"""

QUERY_CATEGORIES = """
query supCategories {
  supCategories {
    id
    name
    parentId
  }
}
"""

QUERY_MANUFACTURERS = """
query supManufacturers {
  supManufacturers {
    id
    name
  }
}
"""


class NexarCollector:
    """Collect part data from the Nexar supply GraphQL API."""

    name = "nexar"

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
            self.settings.nexar_rate_limit_per_minute,
            self.settings.nexar_rate_limit_per_day,
        )
        self.retry = retry or RetryPolicy.from_settings(self.settings)
        self._token = TokenCache(refresh_margin=60.0)

    # ----------------------------------------------------------------------------------
    # Authentication
    # ----------------------------------------------------------------------------------
    def _require_credentials(self) -> None:
        if not self.settings.nexar_client_id or not self.settings.nexar_client_secret:
            raise MissingCredentialsError(
                "Nexar credentials are missing "
                "(PARTPILOT_NEXAR_CLIENT_ID / PARTPILOT_NEXAR_CLIENT_SECRET)"
            )

    async def access_token(self) -> str:
        """Return a valid access token, refreshing it when it expired."""
        cached = self._token.token
        if cached:
            return cached
        self._require_credentials()
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.settings.nexar_client_id,
            "client_secret": self.settings.nexar_client_secret,
            "scope": self.settings.nexar_scope,
        }
        async with http_client(self.settings, self._client) as client:
            response = await request_with_retry(
                self.retry,
                client,
                "POST",
                self.settings.nexar_token_url,
                data=payload,
                headers={"Accept": "application/json"},
            )
        body = response.json()
        token = body.get("access_token")
        if not token:
            raise CollectorError("Nexar did not return an access token")
        self._token.set(token, float(body.get("expires_in", 86400)))
        return str(token)

    # ----------------------------------------------------------------------------------
    # GraphQL
    # ----------------------------------------------------------------------------------
    async def graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Run one GraphQL query and return the whole document."""
        variables = variables or {}
        key = cache_key(self.name, "graphql", query, variables)
        if use_cache:
            cached = self.cache.get(key)
            if cached is not None:
                logger.debug("cache hit for the Nexar query %s", query.strip().splitlines()[0])
                return cached
        token = await self.access_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self.limiter.acquire()
        async with http_client(self.settings, self._client) as client:
            response = await request_with_retry(
                self.retry,
                client,
                "POST",
                self.settings.nexar_graphql_url,
                json={"query": query, "variables": variables},
                headers=headers,
            )
        document = response.json()
        errors = document.get("errors")
        if errors and not document.get("data"):
            raise CollectorError(f"Nexar returned errors: {errors}")
        if use_cache:
            self.cache.put(key, document)
        return document

    # ----------------------------------------------------------------------------------
    # Endpoints
    # ----------------------------------------------------------------------------------
    async def search_mpn(self, mpn: str, limit: int = 25) -> dict[str, Any]:
        """Search one manufacturer part number."""
        return await self.graphql(QUERY_SEARCH_MPN, {"q": mpn, "limit": max(1, int(limit))})

    async def search_keyword(
        self,
        keyword: str,
        limit: int = 25,
        start: int = 0,
        filters: list[str] | None = None,
        sort: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search free text."""
        return await self.graphql(
            QUERY_SEARCH,
            {
                "q": keyword,
                "filters": filters,
                "sort": sort,
                "start": max(0, int(start)),
            },
        )

    async def multi_match(self, mpns: list[str]) -> dict[str, Any]:
        """Look several part numbers up in one request."""
        return await self.graphql(QUERY_MULTI_MATCH, {"queries": list(mpns)})

    async def parts_by_id(self, ids: list[str]) -> dict[str, Any]:
        """Fetch parts by their Nexar ids."""
        return await self.graphql(QUERY_PARTS, {"ids": list(ids)})

    async def categories(self) -> dict[str, Any]:
        """Return the category tree."""
        return await self.graphql(QUERY_CATEGORIES)

    async def manufacturers(self) -> dict[str, Any]:
        """Return the manufacturer list."""
        return await self.graphql(QUERY_MANUFACTURERS)

    # ----------------------------------------------------------------------------------
    # Normalisation
    # ----------------------------------------------------------------------------------
    @staticmethod
    def _results(document: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the ``part`` objects of a search document."""
        data = document.get("data") or {}
        for key in ("supSearchMpn", "supSearch", "supMultiMatch", "supParts"):
            block = data.get(key)
            if isinstance(block, dict):
                results = block.get("results") or []
                return [r.get("part", {}) for r in results if isinstance(r, dict)]
        return []

    def normalize_part(self, part: dict[str, Any]) -> PartRecord:
        """Turn one Nexar part object into a :class:`PartRecord`."""
        mpn = str(part.get("mpn") or "").strip()
        manufacturer = str((part.get("manufacturer") or {}).get("name") or "").strip()
        description = part.get("description") or part.get("name")
        category = (part.get("category") or {}).get("name")
        family = self._family(part, category, description)
        slug = slugify(mpn or str(part.get("id") or ""))
        source_id = f"api-{self.name}-{slug}"
        part_id = f"{family.value.replace('_', '-')}-{slug}"

        parameters = self._parameters(part, part_id, source_id)
        package = next(
            (p.value_text for p in parameters if p.name == "package" and p.value_text),
            None,
        )
        record = PartRecord(
            part_id=part_id,
            mpn=mpn,
            manufacturer=manufacturer,
            family=family,
            package=package,
            lifecycle_status=self._lifecycle(part),
            datasheet_url=self._datasheet_url(part),
            description=str(description) if description else None,
            source_ids=[source_id],
            parameters=parameters,
            updated_at=datetime.now(UTC),
        )
        record.offers = self._offers(part, part_id)
        return record

    def _parameters(
        self,
        part: dict[str, Any],
        part_id: str,
        source_id: str,
    ) -> list[ParameterValue]:
        """Parse the ``specs`` array into parameter values.

        A spec may appear several times (one row per variant). The first row
        that carries a number wins; a row without a number is never used.
        """
        seen: dict[str, ParameterValue] = {}
        for spec in part.get("specs") or []:
            if not isinstance(spec, dict):
                continue
            attribute = spec.get("attribute") or {}
            label = attribute.get("name")
            standard = resolve_parameter_name(label)
            if standard is None and attribute.get("shortname"):
                standard = resolve_parameter_name(str(attribute["shortname"]))
            if standard is None:
                logger.debug("unknown Nexar attribute %r - skipped", label)
                continue
            number, unit = parse_value_with_unit(spec.get("value"))
            if number is None:
                display = spec.get("displayValue")
                number, unit = parse_value_with_unit(display)
            if number is None:
                continue
            if standard in seen:
                continue
            seen[standard] = ParameterValue(
                part_id=part_id,
                name=standard,
                value=number,
                unit=canonical_unit(unit) or unit or spec.get("unitsName"),
                condition=parse_condition(label),
                source_id=source_id,
                page=None,
                method=ExtractionMethod.API,
                confidence=API_CONFIDENCE,
                raw_text=spec.get("displayValue"),
                value_text=spec.get("displayValue"),
            )
        return list(seen.values())

    @staticmethod
    def _datasheet_url(part: dict[str, Any]) -> str | None:
        for document in part.get("documents") or []:
            url = document.get("url") if isinstance(document, dict) else None
            if url:
                return str(url)
        return None

    @staticmethod
    def _lifecycle(part: dict[str, Any]) -> LifecycleStatus:
        status = str((part.get("lifecycle") or {}).get("status") or "").strip().lower()
        if status == "active":
            return LifecycleStatus.ACTIVE
        if status in {"nrnd", "not recommended for new designs"}:
            return LifecycleStatus.NRND
        if status in {"obsolete", "discontinued", "end of life"}:
            return LifecycleStatus.OBSOLETE
        return LifecycleStatus.UNKNOWN

    def _family(
        self,
        part: dict[str, Any],
        category: str | None,
        description: str | None,
    ) -> Family:
        identifier = str(part.get("id") or "")
        if "gate-driver" in identifier or "gate_driver" in identifier:
            return Family.GATE_DRIVER
        if "mosfet" in identifier:
            return Family.MOSFET
        guessed = infer_family(category, description, identifier)
        if guessed:
            return Family(guessed)
        logger.warning("cannot determine the family of %s - assuming mosfet", identifier)
        return Family.MOSFET

    def _offers(self, part: dict[str, Any], part_id: str) -> list[Offer]:
        offers: list[Offer] = []
        for seller in part.get("sellers") or []:
            if not isinstance(seller, dict):
                continue
            company = seller.get("company") or {}
            distributor = str(company.get("name") or "unknown")
            for offer in seller.get("offers") or []:
                if not isinstance(offer, dict):
                    continue
                breaks = [
                    {
                        "quantity": price.get("quantity"),
                        "unit_price": price.get("convertedPrice"),
                        "currency": price.get("convertedCurrency", "USD"),
                    }
                    for price in offer.get("prices") or []
                    if isinstance(price, dict)
                ]
                unit_price = next(
                    (b["unit_price"] for b in breaks if b.get("unit_price") is not None), None
                )
                offers.append(
                    Offer(
                        part_id=part_id,
                        distributor=distributor,
                        sku=offer.get("sku"),
                        stock=offer.get("inventoryLevel"),
                        unit_price=float(unit_price) if unit_price is not None else None,
                        currency=str(breaks[0]["currency"]) if breaks else "USD",
                        price_breaks=breaks,
                        url=None,
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
            document = await self.search_mpn(mpn)
        except HttpStatusError as exc:
            logger.warning("Nexar has no part %s (%s)", mpn, exc)
            return None
        for part in self._results(document):
            if str(part.get("mpn") or "").strip().lower() == mpn.strip().lower():
                return self.normalize_part(part)
        parts = self._results(document)
        if parts:
            return self.normalize_part(parts[0])
        logger.warning("Nexar returned no part for %s", mpn)
        return None

    async def search_by_keyword_async(self, keyword: str, limit: int = 25) -> list[PartRecord]:
        """Return the normalised parts of a keyword search."""
        self._require_credentials()
        document = await self.search_keyword(keyword, limit)
        records = [self.normalize_part(part) for part in self._results(document)]
        return records[:limit]

    async def get_offers_async(self, mpn: str) -> list[dict[str, Any]]:
        """Return the raw distributor offers of ``mpn``."""
        self._require_credentials()
        document = await self.search_mpn(mpn)
        offers: list[dict[str, Any]] = []
        for part in self._results(document):
            for offer in self._offers(part, ""):
                offers.append(
                    {
                        "distributor": offer.distributor,
                        "mpn": mpn,
                        "sku": offer.sku,
                        "stock": offer.stock,
                        "unit_price": offer.unit_price,
                        "currency": offer.currency,
                        "price_breaks": offer.price_breaks,
                        "url": offer.url,
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

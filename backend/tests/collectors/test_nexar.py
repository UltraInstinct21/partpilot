"""Tests of the Nexar (Octopart) GraphQL client."""

from __future__ import annotations

import httpx
import pytest
import respx

from collectors.base import MissingCredentialsError
from collectors.nexar import NexarCollector
from shared.config import Settings
from shared.schemas import Family, LifecycleStatus

TOKEN_URL = "https://identity.nexar.com/connect/token"
GRAPHQL_URL = "https://api.nexar.com/graphql"

TOKEN_RESPONSE = {
    "access_token": "nexar-token",
    "expires_in": 86400,
    "token_type": "Bearer",
    "scope": "supply.domain",
}


def _collector(settings: Settings) -> NexarCollector:
    return NexarCollector(settings)


@pytest.mark.asyncio
async def test_the_token_is_requested_once_and_reused(settings: Settings, load) -> None:
    with respx.mock:
        token = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        graphql = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json=load("nexar/supply_response.json"))
        )
        collector = _collector(settings)
        await collector.search_by_mpn_async("DMN3024U-13")
        await collector.search_by_mpn_async("DMN3024U-13")

    assert token.call_count == 1
    assert graphql.call_count == 1
    request = graphql.calls[0].request
    assert request.headers["Authorization"] == "Bearer nexar-token"


@pytest.mark.asyncio
async def test_the_graphql_response_becomes_a_part_record(settings: Settings, load) -> None:
    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json=load("nexar/supply_response.json"))
        )
        collector = _collector(settings)
        record = await collector.search_by_mpn_async("DMN3024U-13")

    assert record is not None
    assert record.mpn == "DMN3024U-13"
    assert record.manufacturer == "Diodes Incorporated"
    assert record.family is Family.MOSFET
    assert record.lifecycle_status is LifecycleStatus.ACTIVE
    assert record.source_ids == ["api-nexar-dmn3024u-13"]

    values = {p.name: p for p in record.parameters}
    assert values["vds_max"].value == 30.0
    assert values["vds_max"].unit == "V"
    for parameter in record.parameters:
        assert parameter.source_id == "api-nexar-dmn3024u-13"
        assert parameter.method is not None
        assert parameter.confidence > 0


@pytest.mark.asyncio
async def test_the_sellers_become_offers(settings: Settings, load) -> None:
    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json=load("nexar/supply_response.json"))
        )
        collector = _collector(settings)
        record = await collector.search_by_mpn_async("DMN3024U-13")

    assert record is not None
    assert len(record.offers) == 1
    offer = record.offers[0]
    assert offer.distributor == "DigiKey"
    assert offer.sku == "296-DMN3024U-13-ND"
    assert offer.stock == 48213
    assert offer.unit_price == 0.89
    assert offer.price_breaks[1]["quantity"] == 100


@pytest.mark.asyncio
async def test_the_graphql_body_carries_the_query_and_the_variables(
    settings: Settings, load
) -> None:
    import json as jsonlib

    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        graphql = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json=load("nexar/supply_response.json"))
        )
        collector = _collector(settings)
        await collector.search_by_mpn_async("DMN3024U-13")

    body = jsonlib.loads(graphql.calls[0].request.content)
    assert "supSearchMpn" in body["query"]
    assert body["variables"]["q"] == "DMN3024U-13"


@pytest.mark.asyncio
async def test_a_cached_response_makes_no_second_request(settings: Settings, load) -> None:
    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        graphql = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json=load("nexar/supply_response.json"))
        )
        collector = _collector(settings)
        await collector.search_by_mpn_async("DMN3024U-13")
        await collector.search_by_mpn_async("DMN3024U-13")

    assert graphql.call_count == 1
    assert collector.cache.stats().hits == 1


@pytest.mark.asyncio
async def test_a_429_is_retried(settings: Settings, load) -> None:
    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        graphql = respx.post(GRAPHQL_URL).mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=load("nexar/supply_response.json")),
            ]
        )
        collector = _collector(settings)
        record = await collector.search_by_mpn_async("DMN3024U-13")

    assert graphql.call_count == 2
    assert record is not None


def test_the_collector_works_without_credentials(settings: Settings) -> None:
    settings.nexar_client_id = ""
    settings.nexar_client_secret = ""
    collector = _collector(settings)
    with pytest.raises(MissingCredentialsError):
        collector.search_by_mpn("DMN3024U-13")

"""Tests of the Mouser Search API client."""

from __future__ import annotations

import copy
import json as jsonlib

import httpx
import pytest
import respx

from collectors.base import MissingCredentialsError
from collectors.mouser import MouserCollector, parse_bool
from shared.config import Settings
from shared.schemas import Family, LifecycleStatus

PART_URL = "https://api.mouser.com/api/v1/search/partnumber"
KEYWORD_URL = "https://api.mouser.com/api/v1/search/keyword"


def _collector(settings: Settings) -> MouserCollector:
    return MouserCollector(settings)


@pytest.mark.asyncio
async def test_the_part_search_becomes_a_part_record(settings: Settings, load) -> None:
    with respx.mock:
        route = respx.post(PART_URL).mock(
            return_value=httpx.Response(200, json=load("mouser/partnumber_search.json"))
        )
        collector = _collector(settings)
        record = await collector.search_by_mpn_async("UCC27511")

    assert route.call_count == 1
    assert record is not None
    assert record.mpn == "UCC27511"
    assert record.manufacturer == "Texas Instruments"
    assert record.family is Family.GATE_DRIVER
    assert record.lifecycle_status is LifecycleStatus.ACTIVE
    assert record.package == "SOT-23-6"
    assert record.datasheet_url == "https://example.invalid/datasheets/UCC27511.pdf"
    assert record.source_ids == ["api-mouser-ucc27511"]

    values = {p.name: p for p in record.parameters}
    assert values["vds_max"].value == 100.0
    assert values["vds_max"].unit == "V"
    assert values["id_continuous"].value == 25.0
    assert values["rds_on"].value == 5.5
    assert values["rds_on"].unit == "mohm"
    assert values["package"].value_text == "SOT-23-6"

    # The body follows the documented shape.
    body = jsonlib.loads(route.calls[0].request.content)
    assert body["SearchByPartRequest"]["mouserPartNumber"] == "UCC27511"
    assert body["SearchByPartRequest"]["partSearchOptions"] == "Exact"
    # The API key is in the query string and never in the cache.
    assert "apiKey=test-key" in str(route.calls[0].request.url)
    assert all("apiKey" not in str(path) for path in collector.cache.dated_dirs())


@pytest.mark.asyncio
async def test_the_price_breaks_become_an_offer(settings: Settings, load) -> None:
    with respx.mock:
        respx.post(PART_URL).mock(
            return_value=httpx.Response(200, json=load("mouser/partnumber_search.json"))
        )
        collector = _collector(settings)
        offers = await collector.get_offers_async("UCC27511")

    assert len(offers) == 1
    offer = offers[0]
    assert offer["distributor"] == "mouser"
    assert offer["sku"] == "81-UCC27511"
    assert offer["stock"] == 48213
    assert offer["unit_price"] == 0.89
    assert offer["lead_time_days"] == 84
    assert len(offer["price_breaks"]) == 4
    assert offer["price_breaks"][0] == {"quantity": 1, "unit_price": 0.89, "currency": "USD"}
    assert offer["price_breaks"][3]["quantity"] == 1000
    assert offer["is_discontinued"] is False


def test_the_is_discontinued_string_is_parsed_as_a_boolean(settings: Settings, load) -> None:
    document = copy.deepcopy(load("mouser/partnumber_search.json"))
    document["SearchResults"]["Parts"][0]["IsDiscontinued"] = "true"
    with respx.mock:
        respx.post(PART_URL).mock(return_value=httpx.Response(200, json=document))
        collector = _collector(settings)
        record = collector.search_by_mpn("UCC27511")

    assert record is not None
    assert record.lifecycle_status is LifecycleStatus.OBSOLETE


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("True", True),
        ("false", False),
        ("FALSE", False),
        (True, True),
        (False, False),
        ("maybe", None),
        (None, None),
    ],
)
def test_parse_bool(value: object, expected: bool | None) -> None:
    assert parse_bool(value) is expected


@pytest.mark.asyncio
async def test_the_keyword_search_returns_parts(settings: Settings, load) -> None:
    with respx.mock:
        route = respx.post(KEYWORD_URL).mock(
            return_value=httpx.Response(200, json=load("mouser/partnumber_search.json"))
        )
        collector = _collector(settings)
        records = await collector.search_by_keyword_async("gate driver", 3)

    assert route.call_count == 1
    assert len(records) == 3
    body = jsonlib.loads(route.calls[0].request.content)
    assert body["SearchByKeywordRequest"]["keyword"] == "gate driver"
    assert body["SearchByKeywordRequest"]["records"] == 3


@pytest.mark.asyncio
async def test_a_cached_response_makes_no_second_request(settings: Settings, load) -> None:
    with respx.mock:
        route = respx.post(PART_URL).mock(
            return_value=httpx.Response(200, json=load("mouser/partnumber_search.json"))
        )
        collector = _collector(settings)
        await collector.search_by_mpn_async("UCC27511")
        await collector.search_by_mpn_async("UCC27511")

    assert route.call_count == 1
    assert collector.cache.stats().hits == 1


@pytest.mark.asyncio
async def test_a_429_is_retried(settings: Settings, load) -> None:
    with respx.mock:
        route = respx.post(PART_URL).mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=load("mouser/partnumber_search.json")),
            ]
        )
        collector = _collector(settings)
        record = await collector.search_by_mpn_async("UCC27511")

    assert route.call_count == 2
    assert record is not None


def test_the_collector_works_without_credentials(settings: Settings) -> None:
    settings.mouser_api_key = ""
    collector = _collector(settings)
    with pytest.raises(MissingCredentialsError):
        collector.search_by_mpn("UCC27511")

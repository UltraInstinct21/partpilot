"""Tests of the DigiKey v4 client."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from collectors.base import MissingCredentialsError
from collectors.digikey import DigiKeyCollector
from shared.config import Settings
from shared.schemas import Family, LifecycleStatus

TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
DETAILS_URL = "https://api.digikey.com/products/v4/search/IRF3205S/productdetails"

TOKEN_RESPONSE = {
    "access_token": "token-abc",
    "expires_in": 600,
    "token_type": "Bearer",
}


def _collector(settings: Settings) -> DigiKeyCollector:
    return DigiKeyCollector(settings)


@pytest.mark.asyncio
async def test_the_token_is_requested_once_and_then_reused(settings: Settings, load) -> None:
    with respx.mock:
        token = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        details = respx.get(DETAILS_URL).mock(
            return_value=httpx.Response(200, json=load("digikey/product_details.json"))
        )
        other = respx.get("https://api.digikey.com/products/v4/search/IRF540N/productdetails").mock(
            return_value=httpx.Response(200, json=load("digikey/product_details.json"))
        )
        collector = _collector(settings)
        await collector.search_by_mpn_async("IRF3205S")
        await collector.search_by_mpn_async("IRF540N")

    assert token.call_count == 1
    assert details.call_count == 1
    assert other.call_count == 1
    request = details.calls[0].request
    assert request.headers["X-DIGIKEY-Client-Id"] == settings.digikey_client_id
    assert request.headers["Authorization"] == "Bearer token-abc"
    assert request.headers["X-DIGIKEY-Locale-Site"] == settings.digikey_locale_site
    assert request.headers["X-DIGIKEY-Locale-Language"] == settings.digikey_locale_language
    assert request.headers["X-DIGIKEY-Locale-Currency"] == settings.digikey_locale_currency


@pytest.mark.asyncio
async def test_the_token_is_refreshed_before_it_expires(settings: Settings, load) -> None:
    with respx.mock:
        token = respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200, json={"access_token": "token-abc", "expires_in": 30, "token_type": "Bearer"}
            )
        )
        respx.get(DETAILS_URL).mock(
            return_value=httpx.Response(200, json=load("digikey/product_details.json"))
        )
        collector = _collector(settings)
        first = await collector.access_token()
        second = await collector.access_token()

    assert first == "token-abc"
    assert second == "token-abc"
    # The token only lives 30 seconds, so it is refreshed before the next call.
    assert token.call_count == 2


@pytest.mark.asyncio
async def test_a_cached_response_makes_no_second_request(settings: Settings, load) -> None:
    with respx.mock:
        token = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        details = respx.get(DETAILS_URL).mock(
            return_value=httpx.Response(200, json=load("digikey/product_details.json"))
        )
        collector = _collector(settings)
        first = await collector.search_by_mpn_async("IRF3205S")
        second = await collector.search_by_mpn_async("IRF3205S")

    assert token.call_count == 1
    assert details.call_count == 1
    assert first is not None
    assert second is not None
    assert first.part_id == second.part_id
    stats = collector.cache.stats()
    assert stats.hits >= 1
    assert stats.misses == 1


@pytest.mark.asyncio
async def test_the_product_details_become_a_part_record(settings: Settings, load) -> None:
    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        respx.get(DETAILS_URL).mock(
            return_value=httpx.Response(200, json=load("digikey/product_details.json"))
        )
        collector = _collector(settings)
        record = await collector.search_by_mpn_async("IRF3205S")

    assert record is not None
    assert record.mpn == "IRF3205S"
    assert record.manufacturer == "International Rectifier"
    assert record.family is Family.MOSFET
    assert record.package == "TO-220AB"
    assert record.lifecycle_status is LifecycleStatus.ACTIVE
    assert record.datasheet_url == "https://example.invalid/datasheets/IRF3205S.pdf"
    assert record.source_ids == ["api-digikey-irf3205s"]

    values = {p.name: p for p in record.parameters}
    assert values["vds_max"].value == 56.0
    assert values["vds_max"].unit == "V"
    assert values["id_continuous"].value == 3.2
    assert values["id_continuous"].unit == "A"
    assert values["rds_on"].value == 12.0
    assert values["rds_on"].unit == "mohm"
    assert values["vgs_threshold"].value == 2.47
    assert values["vgs_threshold"].unit == "V"
    assert values["total_gate_charge_qg"].value == 37.5
    assert values["total_gate_charge_qg"].unit == "nC"
    assert values["package"].value_text == "TO-220AB"
    # The condition travels with the value (FR-05).
    assert values["id_continuous"].condition == {"Tc": "25 C"}
    # Every value carries its provenance (FR-05).
    for parameter in record.parameters:
        assert parameter.source_id == "api-digikey-irf3205s"
        assert parameter.method is not None
        assert parameter.confidence > 0
    # The name of an unknown label is never guessed.
    assert "mounting_type" not in values


@pytest.mark.asyncio
async def test_a_429_is_retried_and_the_part_is_returned(settings: Settings, load) -> None:
    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        details = respx.get(DETAILS_URL).mock(
            side_effect=[
                httpx.Response(429, json={"error": "too many requests"}),
                httpx.Response(200, json=load("digikey/product_details.json")),
            ]
        )
        collector = _collector(settings)
        record = await collector.search_by_mpn_async("IRF3205S")

    assert details.call_count == 2
    assert record is not None
    assert record.mpn == "IRF3205S"


@pytest.mark.asyncio
async def test_a_404_does_not_raise_but_returns_none(settings: Settings, load) -> None:
    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        respx.get("https://api.digikey.com/products/v4/search/UNKNOWN-PART/productdetails").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        collector = _collector(settings)
        record = await collector.search_by_mpn_async("UNKNOWN-PART")

    assert record is None


@pytest.mark.asyncio
async def test_a_network_error_is_retried(settings: Settings, load) -> None:
    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        details = respx.get(DETAILS_URL).mock(
            side_effect=[
                httpx.ConnectError("connection refused"),
                httpx.Response(200, json=load("digikey/product_details.json")),
            ]
        )
        collector = _collector(settings)
        record = await collector.search_by_mpn_async("IRF3205S")

    assert details.call_count == 2
    assert record is not None


@pytest.mark.asyncio
async def test_a_part_that_always_fails_does_not_raise(settings: Settings, load) -> None:
    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        respx.get(DETAILS_URL).mock(return_value=httpx.Response(503))
        collector = _collector(settings)
        record = await collector.search_by_mpn_async("IRF3205S")

    assert record is None


def test_the_collector_works_without_credentials(settings: Settings, load) -> None:
    settings.digikey_client_id = ""
    settings.digikey_client_secret = ""
    collector = _collector(settings)
    with pytest.raises(MissingCredentialsError):
        collector.search_by_mpn("IRF3205S")


def test_the_synchronous_facade_returns_a_part(settings: Settings, load) -> None:
    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        respx.get(DETAILS_URL).mock(
            return_value=httpx.Response(200, json=load("digikey/product_details.json"))
        )
        collector = _collector(settings)
        record = collector.search_by_mpn("IRF3205S")
    assert record is not None
    assert record.mpn == "IRF3205S"


@pytest.mark.asyncio
async def test_the_offers_are_read_from_the_pricing_endpoint(settings: Settings, load) -> None:
    pricing = {
        "ProductPricing": [
            {"BreakQuantity": 1, "UnitPrice": 0.89, "TotalPrice": 0.89},
            {"BreakQuantity": 100, "UnitPrice": 0.5223, "TotalPrice": 52.23},
        ]
    }
    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        respx.get("https://api.digikey.com/products/v4/search/IRF3205S/pricing").mock(
            return_value=httpx.Response(200, json=pricing)
        )
        collector = _collector(settings)
        offers = await collector.get_offers_async("IRF3205S")

    assert len(offers) == 1
    offer = offers[0]
    assert offer["distributor"] == "digikey"
    assert offer["unit_price"] == 0.89
    assert len(offer["price_breaks"]) == 2
    assert offer["price_breaks"][1]["quantity"] == 100


@pytest.mark.asyncio
async def test_the_keyword_search_returns_parts(settings: Settings, load) -> None:
    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        respx.post("https://api.digikey.com/products/v4/search/keyword").mock(
            return_value=httpx.Response(200, json=load("digikey/keyword_search.json"))
        )
        collector = _collector(settings)
        records = await collector.search_by_keyword_async("MOSFET", 5)

    assert len(records) == 5
    assert {record.mpn for record in records} == {
        "IRF3205S",
        "IRF540N",
        "IRLZ44N",
        "BSC030N08NS5",
        "BSZ084N08NS5",
    }
    assert all(record.family is Family.MOSFET for record in records)


def test_the_raw_response_is_stored_with_the_date(settings: Settings, load) -> None:
    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
        respx.get(DETAILS_URL).mock(
            return_value=httpx.Response(200, json=load("digikey/product_details.json"))
        )
        collector = _collector(settings)
        collector.search_by_mpn("IRF3205S")

    raw = Path(settings.raw_dir) / "digikey"
    assert raw.is_dir()
    dated = list(raw.glob("*/"))
    assert dated
    assert dated[0].name == datetime.now(UTC).strftime("%Y-%m-%d")
    assert list(dated[0].glob("*.json"))

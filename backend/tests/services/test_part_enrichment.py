"""Tests for the on-demand part enrichment used by the compare/details view."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from app.fakes.repository import InMemoryPartsRepository
from services.part_enrichment import PartEnrichmentService, needs_enrichment
from shared.config import Settings
from shared.schemas import (
    ExtractionMethod,
    Family,
    LifecycleStatus,
    Offer,
    ParameterValue,
    PartRecord,
    ValueStatus,
)

THIN_PART_ID = "web-mosfet-thinpart"
THIN_MPN = "THIN123"


def _thin_part() -> PartRecord:
    """A part with no specs, no package, no lifecycle and no datasheet."""
    return PartRecord(
        part_id=THIN_PART_ID,
        mpn=THIN_MPN,
        manufacturer="Unknown (scraped)",
        family=Family.MOSFET,
        package=None,
        lifecycle_status=LifecycleStatus.UNKNOWN,
        datasheet_url=None,
        description=None,
        parameters=[],
        source_ids=[],
    )


def _api_record() -> PartRecord:
    """A rich DigiKey record for the same MPN."""

    def param(name: str, value: float, unit: str) -> ParameterValue:
        return ParameterValue(
            param_id=f"digikey-part::{name}",
            part_id="digikey-part",
            name=name,
            value=value,
            unit=unit,
            confidence=0.9,
            status=ValueStatus.ACCEPTED,
            method=ExtractionMethod.API,
        )

    return PartRecord(
        part_id="mosfet-thin123",
        mpn=THIN_MPN,
        manufacturer="International Rectifier",
        family=Family.MOSFET,
        package="TO-220AB",
        lifecycle_status=LifecycleStatus.ACTIVE,
        datasheet_url="https://www.infineon.com/dgdl/THIN123.pdf",
        description="N-channel power MOSFET",
        source_ids=["api-digikey-thin123"],
        parameters=[
            param("vds_max", 56.0, "V"),
            param("rds_on", 0.012, "ohm"),
            param("id_continuous", 3.2, "A"),
            param("vgs_max", 20.0, "V"),
            param("total_gate_charge_qg", 50e-9, "C"),
        ],
        offers=[
            Offer(
                part_id="digikey-part",
                distributor="digikey",
                sku="DK-THIN123",
                stock=5000,
                unit_price=1.5,
                currency="USD",
            )
        ],
    )


def _settings() -> Settings:
    settings = Settings(_env_file=None)
    settings.digikey_client_id = "test-client"
    settings.digikey_client_secret = SecretStr("test-secret")
    return settings


def test_needs_enrichment_flags_a_thin_part_but_not_a_rich_one() -> None:
    assert needs_enrichment(_thin_part()) is True
    assert needs_enrichment(_api_record()) is False


def test_enrich_fills_a_thin_part_from_the_digikey_api() -> None:
    settings = _settings()
    repo = InMemoryPartsRepository(settings)
    repo.add_part(_thin_part())

    service = PartEnrichmentService(repo, settings)

    mock_collector = MagicMock()
    mock_collector.search_by_mpn.return_value = _api_record()

    mock_web = MagicMock()
    mock_web.deep_scrape_part.return_value = None

    with (
        patch("services.part_enrichment.DigiKeyCollector", return_value=mock_collector),
        patch("services.web_search.WebDiscoveryService", return_value=mock_web),
    ):
        result = service.enrich(THIN_PART_ID)

    # DigiKey was consulted for the MPN.
    mock_collector.search_by_mpn.assert_called_once_with(THIN_MPN)

    assert result is not None
    # Scalar details filled from the API.
    assert result.package == "TO-220AB"
    assert result.lifecycle_status is LifecycleStatus.ACTIVE
    assert result.datasheet_url == "https://www.infineon.com/dgdl/THIN123.pdf"
    assert result.manufacturer == "International Rectifier"
    # Missing specs were added.
    names = {p.name for p in result.parameters}
    assert {"vds_max", "rds_on", "id_continuous", "vgs_max", "total_gate_charge_qg"} <= names
    # The DigiKey offer and provenance are attached.
    assert "digikey" in {o.distributor for o in result.offers}
    assert "api-digikey-thin123" in result.source_ids
    assert repo.get_source("api-digikey-thin123") is not None
    # The merged record was persisted for subsequent requests.
    assert repo.get_part(THIN_PART_ID) is not None


def test_enrich_falls_back_to_scraping_when_the_api_is_unavailable() -> None:
    settings = _settings()
    settings.digikey_client_id = ""  # no credentials -> the API path is skipped
    repo = InMemoryPartsRepository(settings)
    repo.add_part(_thin_part())

    service = PartEnrichmentService(repo, settings)

    mock_collector = MagicMock()
    mock_web = MagicMock()
    scraped = _thin_part()
    scraped.parameters = [
        ParameterValue(
            part_id=THIN_PART_ID,
            name="vds_max",
            value=56.0,
            unit="V",
            confidence=0.85,
            status=ValueStatus.ACCEPTED,
        )
    ]
    scraped.package = "TO-220"
    mock_web.deep_scrape_part.return_value = scraped

    with (
        patch("services.part_enrichment.DigiKeyCollector", return_value=mock_collector),
        patch("services.web_search.WebDiscoveryService", return_value=mock_web),
    ):
        result = service.enrich(THIN_PART_ID)

    # The DigiKey API was never queried without credentials.
    mock_collector.search_by_mpn.assert_not_called()
    assert result is not None
    assert result.package == "TO-220"
    assert {p.name for p in result.parameters} >= {"vds_max"}


def test_a_complete_part_is_returned_untouched_without_any_lookup() -> None:
    settings = _settings()
    repo = InMemoryPartsRepository(settings)
    repo.add_part(_api_record().model_copy(update={"part_id": "mosfet-rich"}))

    service = PartEnrichmentService(repo, settings)

    mock_collector = MagicMock()
    mock_web = MagicMock()
    with (
        patch("services.part_enrichment.DigiKeyCollector", return_value=mock_collector),
        patch("services.web_search.WebDiscoveryService", return_value=mock_web),
    ):
        result = service.enrich("mosfet-rich")

    # A complete part triggers no API call and no scrape at all.
    mock_collector.search_by_mpn.assert_not_called()
    mock_web.deep_scrape_part.assert_not_called()
    assert result is not None
    assert result.package == "TO-220AB"

"""The clients must implement the frozen contract protocols."""

from __future__ import annotations

from collectors.bundle import DefaultCollectorBundle
from collectors.datasheets import DatasheetDownloader as DatasheetDownloaderImpl
from collectors.digikey import DigiKeyCollector
from collectors.mouser import MouserCollector
from collectors.nexar import NexarCollector
from shared.config import Settings
from shared.interfaces import Collector, DatasheetDownloader


def test_every_collector_implements_the_collector_protocol(settings: Settings) -> None:
    for collector in (
        DigiKeyCollector(settings),
        NexarCollector(settings),
        MouserCollector(settings),
    ):
        assert isinstance(collector, Collector)
        assert collector.name
        assert callable(collector.search_by_mpn)
        assert callable(collector.search_by_keyword)
        assert callable(collector.get_offers)


def test_the_downloader_implements_the_datasheet_downloader_protocol(settings: Settings) -> None:
    downloader = DatasheetDownloaderImpl(settings)
    assert isinstance(downloader, DatasheetDownloader)
    assert callable(downloader.download)
    assert callable(downloader.local_path)
    assert callable(downloader.page_count)
    assert callable(downloader.is_scanned)


def test_the_bundle_serves_every_family(settings: Settings) -> None:
    bundle = DefaultCollectorBundle(settings)
    assert {collector.name for collector in bundle.collectors} == {"digikey", "nexar", "mouser"}


def test_the_bundle_picks_the_collectors_of_a_family(settings: Settings) -> None:
    from shared.schemas import Family

    bundle = DefaultCollectorBundle(settings)
    mosfets = {collector.name for collector in bundle.for_family(Family.MOSFET)}
    drivers = {collector.name for collector in bundle.for_family(Family.GATE_DRIVER)}
    assert mosfets == {"digikey", "nexar"}
    assert drivers == {"digikey", "mouser", "nexar"}

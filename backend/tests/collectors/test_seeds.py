"""Tests of the seed list builder."""

from __future__ import annotations

from collectors.seeds import (
    build_seed_list,
    bundled_part_records,
    load_bundled_parts,
    load_bundled_seed,
)
from shared.config import Settings
from shared.schemas import Family


def test_the_bundled_seed_has_thirty_part_numbers(settings: Settings) -> None:
    mpns = load_bundled_seed(settings=settings)
    assert len(mpns) == 30
    assert len(set(mpns)) == 30
    assert "IRF3205S" in mpns
    assert "IR2110" in mpns


def test_the_bundled_seed_is_split_per_family(settings: Settings) -> None:
    mosfets = load_bundled_seed(Family.MOSFET, settings=settings)
    drivers = load_bundled_seed(Family.GATE_DRIVER, settings=settings)
    assert len(mosfets) == 15
    assert len(drivers) == 15
    assert set(mosfets).isdisjoint(drivers)


def test_the_bundled_parts_keep_their_parameters(settings: Settings) -> None:
    parts = load_bundled_parts(Family.MOSFET, settings=settings)
    assert len(parts) == 15
    assert parts[0]["mpn"] == "IRF3205S"
    assert parts[0]["parameters"]["vds_max"]["value"] == 56.0

    records = bundled_part_records(Family.MOSFET, settings=settings)
    assert len(records) == 15
    values = {p.name: p for p in records[0].parameters}
    assert values["vds_max"].value == 56.0
    assert values["vds_max"].unit == "V"
    assert values["vds_max"].source_id == "api-digikey-irf3205s"


def test_the_seed_list_falls_back_to_the_bundle(settings: Settings) -> None:
    mpns = build_seed_list(Family.MOSFET, 10, settings=settings)
    assert len(mpns) == 10
    assert mpns == load_bundled_seed(Family.MOSFET, settings=settings)[:10]


def test_the_seed_list_uses_the_collector_when_it_is_available(settings: Settings) -> None:
    class FakePart:
        def __init__(self, mpn: str) -> None:
            self.mpn = mpn

    class FakeCollector:
        def search_by_keyword(self, keyword: str, limit: int = 25) -> list[FakePart]:
            return [FakePart("FAKE-1"), FakePart("FAKE-2")]

    mpns = build_seed_list(Family.MOSFET, 5, collector=FakeCollector(), settings=settings)
    assert mpns == ["FAKE-1", "FAKE-2"]


def test_the_seed_list_falls_back_when_the_collector_fails(settings: Settings) -> None:
    class BrokenCollector:
        def search_by_keyword(self, keyword: str, limit: int = 25) -> list[object]:
            raise RuntimeError("no network")

    mpns = build_seed_list(Family.GATE_DRIVER, 3, collector=BrokenCollector(), settings=settings)
    assert mpns == load_bundled_seed(Family.GATE_DRIVER, settings=settings)[:3]

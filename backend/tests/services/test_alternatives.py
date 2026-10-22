"""Alternatives service tests (FR-13)."""

from __future__ import annotations

from services.alternatives import AlternativesService
from shared.schemas import Family, LifecycleStatus, Offer, SearchFilter
from tests.services.fakes import (
    FakeLLMExtractor,
    FakePartsRepository,
    make_part,
)

REFERENCE_VALUES = {
    "vds_max": 100.0,
    "rds_on": 12.0,
    "id_continuous": 3.2,
    "total_gate_charge_qg": 37.5,
    "vgs_threshold": 2.47,
    "max_junction_temp": 175.0,
}


def _offer(distributor: str, stock: int) -> Offer:
    return Offer(distributor=distributor, stock=stock, unit_price=1.0, currency="USD")


def _build_repository() -> FakePartsRepository:
    """A small, explicit data set - every value is known."""
    parts = [
        make_part(
            "ref",
            "REF-100",
            package="TO-220AB",
            parameters=dict(REFERENCE_VALUES),
            offers=[_offer("digikey", 5000), _offer("mouser", 4000)],
        ),
        make_part(
            "alt-close",
            "CLOSE-100",
            package="TO-220AB",
            parameters={
                "vds_max": 100.0,
                "rds_on": 12.5,
                "id_continuous": 3.4,
                "total_gate_charge_qg": 38.0,
                "vgs_threshold": 2.5,
                "max_junction_temp": 175.0,
            },
            offers=[_offer("digikey", 5000), _offer("mouser", 4000)],
        ),
        make_part(
            "alt-worse",
            "WORSE-100",
            package="TO-220AB",
            parameters={
                "vds_max": 100.0,
                "rds_on": 30.0,
                "id_continuous": 5.0,
                "total_gate_charge_qg": 60.0,
                "vgs_threshold": 2.8,
                "max_junction_temp": 150.0,
            },
            offers=[_offer("digikey", 100), _offer("mouser", 50)],
        ),
        make_part(
            "alt-low-voltage",
            "LOWV-100",
            package="TO-220AB",
            parameters={
                "vds_max": 60.0,
                "rds_on": 8.0,
                "id_continuous": 4.0,
                "total_gate_charge_qg": 30.0,
                "vgs_threshold": 2.4,
                "max_junction_temp": 175.0,
            },
            offers=[_offer("digikey", 9000), _offer("mouser", 9000)],
        ),
        make_part(
            "alt-obsolete",
            "OBS-100",
            package="TO-220AB",
            lifecycle=LifecycleStatus.OBSOLETE,
            parameters={
                "vds_max": 150.0,
                "rds_on": 5.0,
                "id_continuous": 6.0,
                "total_gate_charge_qg": 25.0,
                "vgs_threshold": 2.3,
                "max_junction_temp": 175.0,
            },
            offers=[_offer("digikey", 10)],
        ),
        make_part(
            "alt-other-package",
            "OTHER-100",
            package="TO-263",
            parameters={
                "vds_max": 200.0,
                "rds_on": 5.0,
                "id_continuous": 6.0,
                "total_gate_charge_qg": 25.0,
                "vgs_threshold": 2.3,
                "max_junction_temp": 175.0,
            },
            offers=[_offer("digikey", 9000), _offer("mouser", 9000)],
        ),
    ]
    return FakePartsRepository(parts)


def test_only_the_same_family_and_package_is_accepted() -> None:
    service = AlternativesService(_build_repository())

    results = service.alternatives("ref", limit=10)

    accepted = [item for item in results if not item.rejected]
    assert {item.part.part_id for item in accepted} == {"alt-close", "alt-worse"}
    assert all(item.part.family == Family.MOSFET for item in accepted)
    assert all(item.part.package == "TO-220AB" for item in accepted)


def test_a_lower_voltage_rating_is_a_hard_rejection() -> None:
    service = AlternativesService(_build_repository())

    results = service.alternatives("ref", limit=10)

    rejected = {item.part.part_id: item for item in results if item.rejected}
    assert "alt-low-voltage" in rejected
    assert "Vds" in (rejected["alt-low-voltage"].rejection_reason or "")
    assert rejected["alt-low-voltage"].rank > max(
        item.rank for item in results if not item.rejected
    )


def test_an_obsolete_part_is_a_hard_rejection() -> None:
    service = AlternativesService(_build_repository())

    results = service.alternatives("ref", limit=10)

    rejected = {item.part.part_id: item for item in results if item.rejected}
    assert "obsolete" in (rejected["alt-obsolete"].rejection_reason or "").lower()


def test_a_different_package_is_a_hard_rejection_when_one_matches() -> None:
    service = AlternativesService(_build_repository())

    results = service.alternatives("ref", limit=10)

    rejected = {item.part.part_id: item for item in results if item.rejected}
    assert "package" in (rejected["alt-other-package"].rejection_reason or "").lower()


def test_the_accepted_candidates_are_ranked_by_the_distance() -> None:
    service = AlternativesService(_build_repository())

    results = service.alternatives("ref", limit=10)

    accepted = [item for item in results if not item.rejected]
    assert [item.part.part_id for item in accepted] == ["alt-close", "alt-worse"]
    assert accepted[0].rank == 1
    assert accepted[0].score > accepted[1].score


def test_the_reason_is_short_and_names_the_differing_fields() -> None:
    service = AlternativesService(_build_repository())

    results = service.alternatives("ref", limit=10)

    close = next(item for item in results if item.part.part_id == "alt-close")
    assert close.reason
    assert len(close.reason) < 80
    assert "Rds(on)" in close.reason


def test_the_differences_are_populated() -> None:
    service = AlternativesService(_build_repository())

    results = service.alternatives("ref", limit=10)

    close = next(item for item in results if item.part.part_id == "alt-close")
    assert close.differences["rds_on"] == {"reference": 12.0, "candidate": 12.5}
    assert close.differences["vds_max"] == {"reference": 100.0, "candidate": 100.0}
    assert "rds_on" in close.differences


def test_stock_and_lifecycle_change_the_score() -> None:
    parts = [
        make_part(
            "ref",
            "REF-100",
            parameters=dict(REFERENCE_VALUES),
            offers=[_offer("digikey", 5000)],
        ),
        make_part(
            "alt-rich",
            "RICH-100",
            package="TO-220AB",
            parameters=dict(REFERENCE_VALUES),
            offers=[_offer("digikey", 50000)],
        ),
        make_part(
            "alt-poor",
            "POOR-100",
            package="TO-220AB",
            parameters=dict(REFERENCE_VALUES),
            offers=[_offer("digikey", 1)],
        ),
    ]
    service = AlternativesService(FakePartsRepository(parts))

    results = service.alternatives("ref", limit=10)
    rich = next(item for item in results if item.part.part_id == "alt-rich")
    poor = next(item for item in results if item.part.part_id == "alt-poor")

    assert rich.score > poor.score
    assert rich.rank == 1


def test_a_nrnd_part_gets_a_smaller_bonus_than_an_active_part() -> None:
    parts = [
        make_part("ref", "REF-100", parameters=dict(REFERENCE_VALUES)),
        make_part(
            "alt-active",
            "ACTIVE-100",
            package="TO-220AB",
            parameters=dict(REFERENCE_VALUES),
        ),
        make_part(
            "alt-nrnd",
            "NRND-100",
            package="TO-220AB",
            lifecycle=LifecycleStatus.NRND,
            parameters=dict(REFERENCE_VALUES),
        ),
    ]
    service = AlternativesService(FakePartsRepository(parts))

    results = service.alternatives("ref", limit=10)
    active = next(item for item in results if item.part.part_id == "alt-active")
    nrnd = next(item for item in results if item.part.part_id == "alt-nrnd")

    assert active.score > nrnd.score


def test_an_unknown_part_id_returns_an_empty_list() -> None:
    service = AlternativesService(_build_repository())

    assert service.alternatives("does-not-exist") == []


def test_the_family_falls_back_when_no_part_shares_the_package() -> None:
    parts = [
        make_part(
            "ref",
            "REF-100",
            package="DSBGA-8",
            parameters=dict(REFERENCE_VALUES),
        ),
        make_part(
            "alt-other-package",
            "OTHER-100",
            package="TO-263",
            parameters={
                "vds_max": 150.0,
                "rds_on": 5.0,
                "id_continuous": 6.0,
                "total_gate_charge_qg": 25.0,
                "vgs_threshold": 2.3,
                "max_junction_temp": 175.0,
            },
        ),
    ]
    service = AlternativesService(FakePartsRepository(parts))

    results = service.alternatives("ref", limit=10)

    assert len(results) == 1
    assert results[0].rejected is False
    assert results[0].part.package == "TO-263"


def test_a_different_family_is_rejected() -> None:
    class LooseRepository(FakePartsRepository):
        """A repository that ignores the family filter (for the hard rule test)."""

        def list_parts(
            self,
            filt: SearchFilter | None = None,
            limit: int = 50,
            offset: int = 0,
        ) -> tuple[list, int]:
            self._record("list_parts", filt, limit=limit, offset=offset)
            summaries = [self._summary(part) for part in self._parts.values()]
            return summaries, len(summaries)

    parts = [
        make_part("ref", "REF-100", parameters=dict(REFERENCE_VALUES)),
        make_part(
            "alt-driver",
            "DRV-1",
            family=Family.GATE_DRIVER,
            package="TO-220AB",
            parameters={"supply_voltage_max": 20.0},
        ),
    ]
    service = AlternativesService(LooseRepository(parts))

    results = service.alternatives("ref", limit=10)

    rejected = {item.part.part_id: item for item in results if item.rejected}
    assert "family" in (rejected["alt-driver"].rejection_reason or "").lower()


def test_the_llm_may_polish_the_reason_when_explain_is_true() -> None:
    llm = FakeLLMExtractor(explanation="Almost a drop-in replacement.")
    service = AlternativesService(_build_repository(), llm)

    results = service.alternatives("ref", limit=10, explain=True)

    assert llm.call_counts["explain_alternative"] >= 1
    assert results[0].reason == "Almost a drop-in replacement."


def test_the_llm_is_not_called_when_explain_is_false() -> None:
    llm = FakeLLMExtractor()
    service = AlternativesService(_build_repository(), llm)

    service.alternatives("ref", limit=10, explain=False)

    assert llm.call_counts["explain_alternative"] == 0


def test_a_broken_llm_falls_back_to_the_generated_reason() -> None:
    llm = FakeLLMExtractor(raise_on_explain=True)
    service = AlternativesService(_build_repository(), llm)

    results = service.alternatives("ref", limit=10, explain=True)

    assert "Rds(on)" in results[0].reason


def test_an_llm_that_invents_a_number_is_ignored() -> None:
    llm = FakeLLMExtractor(explanation="Rds(on) is 3.3 mohm instead of 12 mohm.")
    service = AlternativesService(_build_repository(), llm)

    results = service.alternatives("ref", limit=10, explain=True)

    assert "Rds(on)" in results[0].reason
    assert "3.3" not in results[0].reason


def test_the_seed_data_produces_alternatives() -> None:
    repo = FakePartsRepository()
    service = AlternativesService(repo)

    results = service.alternatives("mosfet-irf3205s", limit=10)

    accepted = [item for item in results if not item.rejected]
    assert accepted
    assert accepted[0].part.part_id == "mosfet-stp55nf06l"
    assert all(item.part.package == "TO-220AB" for item in accepted)


def test_a_gate_driver_reference_uses_the_gate_driver_rules() -> None:
    repo = FakePartsRepository()
    service = AlternativesService(repo)

    results = service.alternatives("gate-driver-ir2104", limit=10)

    accepted = [item for item in results if not item.rejected]
    rejected = {item.part.part_id: item for item in results if item.rejected}
    assert accepted
    assert all(item.part.family == Family.GATE_DRIVER for item in accepted)
    # MAX4429 has a much lower supply voltage than the reference.
    assert "supply voltage" in (rejected["gate-driver-max4429"].rejection_reason or "")

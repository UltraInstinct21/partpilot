"""CRUD of parts, values, sources and offers."""

from __future__ import annotations

from pathlib import Path

import pytest

from db.repository import SqlAlchemyPartsRepository
from shared.schemas import (
    ExtractionMethod,
    Family,
    LifecycleStatus,
    ParameterValue,
    SourceType,
    ValueStatus,
)
from tests.db.conftest import make_part, make_value

FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "fixtures"


def test_add_part_round_trip_keeps_the_provenance(repo, source) -> None:
    repo.add_source(source)
    value = make_value(
        "rds_on",
        0.012,
        "ohm",
        source_id=source.source_id,
        page=3,
        method=ExtractionMethod.TIER2,
        confidence=0.82,
        status=ValueStatus.ACCEPTED,
        condition={"Vgs": "10 V", "Tj": "25 C"},
        raw_text="RDS(on) 12 mOhm",
    )
    part = make_part(parameters=[value], source_ids=[source.source_id])

    stored = repo.add_part(part)
    assert stored.part_id == "part-1"
    assert stored.mpn == "IRF3205S"
    assert stored.family is Family.MOSFET
    assert stored.lifecycle_status is LifecycleStatus.ACTIVE
    assert stored.source_ids == [source.source_id]

    fetched = repo.get_part("part-1")
    assert fetched is not None
    assert len(fetched.parameters) == 1
    kept = fetched.parameters[0]
    assert kept.name == "rds_on"
    assert kept.value == 0.012
    assert kept.unit == "ohm"
    assert kept.source_id == source.source_id
    assert kept.page == 3
    assert kept.method is ExtractionMethod.TIER2
    assert kept.confidence == 0.82
    assert kept.status is ValueStatus.ACCEPTED
    assert kept.condition == {"Vgs": "10 V", "Tj": "25 C"}
    assert kept.raw_text == "RDS(on) 12 mOhm"
    assert kept.part_id == "part-1"


def test_add_part_is_idempotent(repo) -> None:
    part = make_part(parameters=[make_value("vds_max", 56.0, "V")])
    repo.add_part(part)
    repo.add_part(part)
    assert len(repo.get_part("part-1").parameters) == 1


def test_get_part_returns_none_for_an_unknown_id(repo) -> None:
    assert repo.get_part("does-not-exist") is None


def test_get_part_by_mpn(repo) -> None:
    repo.add_part(make_part(part_id="p1", mpn="IRF3205S"))
    repo.add_part(make_part(part_id="p2", mpn="IRF540N", manufacturer="Vishay"))
    found = repo.get_part_by_mpn("IRF540N")
    assert found is not None
    assert found.part_id == "p2"
    assert repo.get_part_by_mpn("NOPE") is None


def test_get_parameters_returns_every_status(repo) -> None:
    repo.add_part(
        make_part(
            parameters=[
                make_value("vds_max", 56.0, "V", status=ValueStatus.ACCEPTED),
                make_value("rds_on", 0.012, "ohm", status=ValueStatus.REVIEW),
                make_value("vgs_max", 20.0, "V", status=ValueStatus.REJECTED),
            ]
        )
    )
    values = repo.get_parameters("part-1")
    assert {value.name for value in values} == {"vds_max", "rds_on", "vgs_max"}
    assert len(values) == 3


def test_get_parameter_by_id(repo) -> None:
    repo.add_part(make_part(parameters=[make_value("vds_max", 56.0, "V")]))
    param_id = repo.get_parameters("part-1")[0].param_id
    value = repo.get_parameter(param_id)
    assert value is not None
    assert value.name == "vds_max"
    assert repo.get_parameter("nope") is None


def test_update_parameter_persists_status_and_confidence(repo) -> None:
    repo.add_part(
        make_part(parameters=[make_value("vds_max", 56.0, "V", status=ValueStatus.REVIEW)])
    )
    value = repo.get_parameters("part-1")[0]
    value.status = ValueStatus.ACCEPTED
    value.confidence = 0.95
    value.method = ExtractionMethod.TIER3
    updated = repo.update_parameter(value)
    assert updated.status is ValueStatus.ACCEPTED
    assert updated.confidence == 0.95
    assert updated.method is ExtractionMethod.TIER3

    reread = repo.get_parameter(value.param_id)
    assert reread.status is ValueStatus.ACCEPTED
    assert reread.confidence == 0.95
    assert reread.method is ExtractionMethod.TIER3


def test_update_parameter_needs_an_id(repo) -> None:
    with pytest.raises(ValueError):
        repo.update_parameter(ParameterValue(name="vds_max", value=1.0))


def test_update_parameter_of_an_unknown_id_raises(repo) -> None:
    with pytest.raises(KeyError):
        repo.update_parameter(ParameterValue(param_id="nope", name="vds_max", value=1.0))


def test_add_and_get_source(repo, source) -> None:
    stored = repo.add_source(source)
    assert stored.source_id == source.source_id
    assert stored.type is SourceType.PDF
    assert stored.page_count == 12
    assert stored.file_hash == "deadbeef"

    fetched = repo.get_source(source.source_id)
    assert fetched is not None
    assert fetched.url == source.url
    assert fetched.distributor == "digikey"
    assert fetched.content_type == "application/pdf"
    assert fetched.fetched_at == source.fetched_at
    assert repo.get_source("nope") is None


def test_get_source_page_returns_a_page(repo, source) -> None:
    repo.add_source(source)
    page = repo.get_source_page(source.source_id, 1)
    assert page is not None
    assert page.source_id == source.source_id
    assert page.page == 1
    assert repo.get_source_page("nope", 1) is None


def test_add_source_page_caches_the_text(repo, source) -> None:
    repo.add_source(source)
    repo.add_source_page(source.source_id, 2, "Absolute Maximum Ratings", width=612, height=792)
    page = repo.get_source_page(source.source_id, 2)
    assert page is not None
    assert page.text == "Absolute Maximum Ratings"
    assert page.width == 612
    assert page.height == 792


def test_get_source_page_reads_a_local_pdf(repo, source) -> None:
    pdf = FIXTURES / "pdfs" / "synthetic_mosfet.pdf"
    assert pdf.exists()
    repo.add_source(source.model_copy(update={"local_path": str(pdf)}))
    page = repo.get_source_page(source.source_id, 1)
    assert page is not None
    assert page.text, "the synthetic PDF has a text layer"
    assert page.width and page.height
    assert page.is_image_only is False


def test_get_source_page_without_a_file_has_no_text(repo, source) -> None:
    repo.add_source(source.model_copy(update={"local_path": "/does/not/exist.pdf"}))
    page = repo.get_source_page(source.source_id, 1)
    assert page is not None
    assert page.text is None


def test_add_offer_stores_the_offer(repo) -> None:
    repo.add_part(make_part())
    repo.add_offer(
        "part-1",
        {
            "distributor": "digikey",
            "sku": "705-IRF3205S",
            "stock": 1250,
            "unit_price": 1.23,
            "price_breaks": [{"quantity": 10, "price": 1.1}],
            "lead_time_days": 3,
            "url": "https://example.invalid/offer/1",
        },
    )
    part = repo.get_part("part-1")
    assert len(part.offers) == 1
    offer = part.offers[0]
    assert offer.distributor == "digikey"
    assert offer.stock == 1250
    assert offer.unit_price == 1.23
    assert offer.currency == "USD"
    assert offer.price_breaks == [{"quantity": 10, "price": 1.1}]
    assert offer.lead_time_days == 3


def test_add_offer_is_idempotent_per_distributor_and_sku(repo) -> None:
    repo.add_part(make_part())
    payload = {"distributor": "digikey", "sku": "705-IRF3205S", "stock": 10}
    repo.add_offer("part-1", payload)
    repo.add_offer("part-1", {**payload, "stock": 20})
    part = repo.get_part("part-1")
    assert len(part.offers) == 1
    assert part.offers[0].stock == 20


def test_add_part_with_an_unknown_source_is_refused(repo) -> None:
    """The foreign key of the reference schema is enforced with a clear error."""
    part = make_part(parameters=[make_value("vds_max", 56.0, "V", source_id="nope")])
    with pytest.raises(ValueError, match="unknown source_id"):
        repo.add_part(part)


def test_repository_can_use_an_external_session(engine) -> None:
    from db.session import make_session_factory

    session = make_session_factory(engine)()
    try:
        repository = SqlAlchemyPartsRepository(session)
        repository.add_part(make_part())
        assert repository.get_part("part-1") is not None
        session.commit()
    finally:
        session.close()

"""The seed loader (idempotent, canonical units, synthetic provenance)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from db.models import NameMapRow, ParameterRow, PartRow, SourceRow
from db.repository import NameMapRepository
from db.seed import DEFAULT_NAME_MAP_PATH, DEFAULT_SEED_PATH, load_seed, main
from shared.schemas import ExtractionMethod, Family, ValueStatus

FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "fixtures"


def test_default_paths_exist() -> None:
    assert DEFAULT_SEED_PATH.exists()
    assert DEFAULT_NAME_MAP_PATH.exists()


def test_load_seed_loads_the_thirty_parts(engine) -> None:
    summary = load_seed(engine)
    assert summary["parts"] == 30
    with engine.connect() as connection:
        parts = connection.scalar(select(func.count()).select_from(PartRow))
        parameters = connection.scalar(select(func.count()).select_from(ParameterRow))
        sources = connection.scalar(select(func.count()).select_from(SourceRow))
    assert parts == 30
    assert parameters == summary["parameters"] == 390  # 13 values per part
    assert sources == 60  # two api sources per part


def test_load_seed_is_idempotent(engine) -> None:
    load_seed(engine)
    with engine.connect() as connection:
        parts_before = connection.scalar(select(func.count()).select_from(PartRow))
        parameters_before = connection.scalar(select(func.count()).select_from(ParameterRow))
        sources_before = connection.scalar(select(func.count()).select_from(SourceRow))
    load_seed(engine)
    load_seed(engine)
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(PartRow)) == parts_before
        assert (
            connection.scalar(select(func.count()).select_from(ParameterRow)) == parameters_before
        )
        assert connection.scalar(select(func.count()).select_from(SourceRow)) == sources_before
    assert parts_before == 30


def test_seeded_parts_keep_their_provenance(repo, engine) -> None:
    load_seed(engine)
    part = repo.get_part("mosfet-irf3205s")
    assert part is not None
    assert part.mpn == "IRF3205S"
    assert part.family is Family.MOSFET
    assert part.source_ids == ["api-digikey-irf3205s", "api-nexar-irf3205s"]

    values = {value.name: value for value in part.parameters}
    vds_max = values["vds_max"]
    assert vds_max.value == 56.0
    assert vds_max.unit == "V"
    assert vds_max.method is ExtractionMethod.API
    assert vds_max.confidence == 0.9
    assert vds_max.status is ValueStatus.ACCEPTED
    assert vds_max.source_id == "api-digikey-irf3205s"
    assert vds_max.condition == {}


def test_seeded_units_are_canonical(repo, engine) -> None:
    load_seed(engine)
    part = repo.get_part("mosfet-irf3205s")
    values = {value.name: value for value in part.parameters}
    assert values["rds_on"].unit == "ohm"
    assert values["rds_on"].value == pytest.approx(0.012)
    assert values["total_gate_charge_qg"].unit == "C"
    assert values["total_gate_charge_qg"].value == pytest.approx(3.75e-08)
    assert values["input_capacitance_ciss"].unit == "F"
    assert values["input_capacitance_ciss"].value == pytest.approx(8.75e-09)


def test_a_value_without_a_number_goes_to_the_review_queue(repo, engine) -> None:
    load_seed(engine)
    part = repo.get_part("mosfet-irf3205s")
    values = {value.name: value for value in part.parameters}
    assert values["package"].value is None
    assert values["package"].status is ValueStatus.REVIEW
    assert len(repo.list_review_queue()) == 30  # one per part


def test_the_seeded_parts_can_be_searched(repo, engine) -> None:
    load_seed(engine)
    rows, total = repo.list_parts()
    assert total == 30
    assert len(rows) == 30

    from shared.schemas import ParameterConstraint, SearchFilter

    filt = SearchFilter(
        family=Family.MOSFET,
        parameters=[
            ParameterConstraint(name="vds_max", operator="lte", max=100.0, unit="V"),
        ],
    )
    rows, total = repo.list_parts(filt)
    assert total > 0
    assert all(row.family is Family.MOSFET for row in rows)
    assert all(row.key_parameters["vds_max"] <= 100.0 for row in rows)


def test_the_seed_loads_the_name_map(engine) -> None:
    summary = load_seed(engine)
    assert summary["name_map"] > 0
    name_map = NameMapRepository(engine)
    assert name_map.lookup("Drain to Source Voltage (Vdss)", "mosfet") == "vds_max"
    assert name_map.lookup("Total Gate Charge (Qg)", "mosfet") == "total_gate_charge_qg"
    with engine.connect() as connection:
        rows = connection.scalar(select(func.count()).select_from(NameMapRow))
    assert rows == summary["name_map"]


def test_main_loads_the_seed_into_a_database(tmp_path: Path) -> None:
    database = tmp_path / "seed.db"
    exit_code = main(["--database-url", f"sqlite:///{database}"])
    assert exit_code == 0
    assert database.exists()

    from db.session import create_engine_for_url, init_db

    engine = create_engine_for_url(f"sqlite:///{database}")
    init_db(engine)
    with engine.connect() as connection:
        parts = connection.scalar(select(func.count()).select_from(PartRow))
    assert parts == 30

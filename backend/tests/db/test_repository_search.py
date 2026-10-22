"""``list_parts`` - the SearchFilter is translated into SQL."""

from __future__ import annotations

from shared.schemas import (
    Family,
    LifecycleStatus,
    ParameterConstraint,
    SearchFilter,
)
from tests.db.conftest import make_part, make_value


def _seed(repo) -> None:
    """Three MOSFETs and one gate driver with a few values each."""
    repo.add_part(
        make_part(
            part_id="m1",
            mpn="IRF3205S",
            manufacturer="International Rectifier",
            package="TO-220AB",
            lifecycle_status=LifecycleStatus.ACTIVE,
            parameters=[
                make_value("vds_max", 56.0, "V"),
                make_value("id_continuous", 3.2, "A"),
                make_value("rds_on", 0.012, "ohm"),
                make_value("total_gate_charge_qg", 3.75e-08, "C"),
            ],
        )
    )
    repo.add_part(
        make_part(
            part_id="m2",
            mpn="BSC030N08NS5",
            manufacturer="Infineon Technologies",
            package="SuperSO8",
            lifecycle_status=LifecycleStatus.ACTIVE,
            description="80 V OptiMOS",
            parameters=[
                make_value("vds_max", 80.0, "V"),
                make_value("id_continuous", 30.0, "A"),
                make_value("rds_on", 0.003, "ohm"),
                make_value("total_gate_charge_qg", 1.2e-07, "C"),
            ],
        )
    )
    repo.add_part(
        make_part(
            part_id="m3",
            mpn="OLD123",
            manufacturer="International Rectifier",
            package="TO-263",
            lifecycle_status=LifecycleStatus.OBSOLETE,
            parameters=[
                make_value("vds_max", 100.0, "V"),
                make_value("rds_on", 0.05, "ohm"),
            ],
        )
    )
    repo.add_part(
        make_part(
            part_id="g1",
            mpn="IR2110",
            manufacturer="International Rectifier",
            family=Family.GATE_DRIVER,
            package="SOIC-8",
            lifecycle_status=LifecycleStatus.ACTIVE,
            description="High side gate driver",
            parameters=[
                make_value("supply_voltage_min", 4.5, "V"),
                make_value("supply_voltage_max", 20.0, "V"),
                make_value("peak_source_current", 2.0, "A"),
                make_value("propagation_delay", 2e-07, "s"),
            ],
        )
    )


def _mpns(rows) -> list[str]:
    return sorted(row.mpn for row in rows)


def test_no_filter_returns_everything(repo) -> None:
    _seed(repo)
    rows, total = repo.list_parts()
    assert total == 4
    assert len(rows) == 4


def test_filter_on_family(repo) -> None:
    _seed(repo)
    rows, total = repo.list_parts(SearchFilter(family=Family.MOSFET))
    assert total == 3
    assert _mpns(rows) == ["BSC030N08NS5", "IRF3205S", "OLD123"]


def test_filter_on_manufacturer(repo) -> None:
    _seed(repo)
    rows, total = repo.list_parts(SearchFilter(manufacturer="international rectifier"))
    assert total == 3
    assert _mpns(rows) == ["IR2110", "IRF3205S", "OLD123"]


def test_filter_on_manufacturer_in(repo) -> None:
    _seed(repo)
    rows, total = repo.list_parts(SearchFilter(manufacturer_in=["Infineon Technologies"]))
    assert total == 1
    assert _mpns(rows) == ["BSC030N08NS5"]


def test_filter_on_package(repo) -> None:
    _seed(repo)
    rows, total = repo.list_parts(SearchFilter(package="superSO8"))
    assert total == 1
    assert _mpns(rows) == ["BSC030N08NS5"]


def test_filter_on_package_in(repo) -> None:
    _seed(repo)
    rows, total = repo.list_parts(SearchFilter(package_in=["TO-263", "SOIC-8"]))
    assert total == 2
    assert _mpns(rows) == ["IR2110", "OLD123"]


def test_filter_on_lifecycle(repo) -> None:
    _seed(repo)
    rows, total = repo.list_parts(SearchFilter(lifecycle_status=[LifecycleStatus.OBSOLETE]))
    assert total == 1
    assert _mpns(rows) == ["OLD123"]


def test_filter_on_mpn_contains_is_case_insensitive(repo) -> None:
    _seed(repo)
    rows, total = repo.list_parts(SearchFilter(mpn_contains="irf"))
    assert total == 1
    assert _mpns(rows) == ["IRF3205S"]

    rows, total = repo.list_parts(SearchFilter(mpn_contains="ir2"))
    assert total == 1
    assert _mpns(rows) == ["IR2110"]


def test_filter_on_text_searches_mpn_description_and_manufacturer(repo) -> None:
    _seed(repo)
    rows, total = repo.list_parts(SearchFilter(text="optimos"))
    assert total == 1
    assert _mpns(rows) == ["BSC030N08NS5"]

    rows, total = repo.list_parts(SearchFilter(text="infineon"))
    assert total == 1
    assert _mpns(rows) == ["BSC030N08NS5"]

    rows, total = repo.list_parts(SearchFilter(text="IR2110"))
    assert total == 1
    assert _mpns(rows) == ["IR2110"]


def test_filter_on_in_stock(repo) -> None:
    _seed(repo)
    repo.add_offer("m2", {"distributor": "digikey", "sku": "1", "stock": 500})
    repo.add_offer("m1", {"distributor": "digikey", "sku": "2", "stock": 0})

    rows, total = repo.list_parts(SearchFilter(in_stock=True))
    assert total == 1
    assert _mpns(rows) == ["BSC030N08NS5"]

    rows, total = repo.list_parts(SearchFilter(in_stock=False))
    assert total == 3
    assert "BSC030N08NS5" not in _mpns(rows)


def test_filter_on_a_parameter_constraint(repo) -> None:
    _seed(repo)
    filt = SearchFilter(
        parameters=[ParameterConstraint(name="vds_max", operator="lte", max=100.0, unit="V")]
    )
    rows, total = repo.list_parts(filt)
    assert total == 3
    assert _mpns(rows) == ["BSC030N08NS5", "IRF3205S", "OLD123"]


def test_parameter_constraint_converts_the_unit(repo) -> None:
    """``5 mohm`` has to match the canonical ``0.005 ohm``."""
    _seed(repo)
    filt = SearchFilter(
        parameters=[ParameterConstraint(name="rds_on", operator="lte", max=5.0, unit="mohm")]
    )
    rows, total = repo.list_parts(filt)
    assert total == 1
    assert _mpns(rows) == ["BSC030N08NS5"]

    filt = SearchFilter(
        parameters=[ParameterConstraint(name="rds_on", operator="lte", max=0.005, unit="ohm")]
    )
    rows, total = repo.list_parts(filt)
    assert total == 1
    assert _mpns(rows) == ["BSC030N08NS5"]


def test_parameter_constraint_without_a_unit_uses_the_canonical_unit(repo) -> None:
    _seed(repo)
    filt = SearchFilter(parameters=[ParameterConstraint(name="rds_on", operator="lte", max=0.005)])
    rows, total = repo.list_parts(filt)
    assert total == 1
    assert _mpns(rows) == ["BSC030N08NS5"]


def test_parameter_constraint_operators(repo) -> None:
    _seed(repo)

    def run(**kwargs):
        filt = SearchFilter(parameters=[ParameterConstraint(name="vds_max", **kwargs)])
        rows, total = repo.list_parts(filt)
        return total, _mpns(rows)

    total, mpns = run(operator="lt", max=80.0, unit="V")
    assert total == 1 and mpns == ["IRF3205S"]

    total, mpns = run(operator="lte", max=80.0, unit="V")
    assert total == 2 and mpns == ["BSC030N08NS5", "IRF3205S"]

    total, mpns = run(operator="gt", min=80.0, unit="V")
    assert total == 1 and mpns == ["OLD123"]

    total, mpns = run(operator="gte", min=80.0, unit="V")
    assert total == 2 and mpns == ["BSC030N08NS5", "OLD123"]

    total, mpns = run(operator="eq", typ=56.0, unit="V")
    assert total == 1 and mpns == ["IRF3205S"]

    total, mpns = run(operator="between", min=60.0, max=90.0, unit="V")
    assert total == 1 and mpns == ["BSC030N08NS5"]


def test_parameter_constraints_are_combined_with_and(repo) -> None:
    _seed(repo)
    filt = SearchFilter(
        parameters=[
            ParameterConstraint(name="vds_max", operator="gte", min=60.0, unit="V"),
            ParameterConstraint(name="rds_on", operator="lte", max=0.01, unit="ohm"),
        ]
    )
    rows, total = repo.list_parts(filt)
    assert total == 1
    assert _mpns(rows) == ["BSC030N08NS5"]


def test_total_is_the_count_before_limit_and_offset(repo) -> None:
    _seed(repo)
    rows, total = repo.list_parts(limit=1, offset=0)
    assert len(rows) == 1
    assert total == 4

    rows, total = repo.list_parts(limit=2, offset=2)
    assert len(rows) == 2
    assert total == 4


def test_summary_carries_the_key_parameters(repo) -> None:
    _seed(repo)
    rows, _ = repo.list_parts(SearchFilter(mpn_contains="IRF3205S"))
    assert len(rows) == 1
    summary = rows[0]
    assert summary.key_parameters["vds_max"] == 56.0
    assert summary.key_parameters["id_continuous"] == 3.2
    assert summary.key_parameters["rds_on"] == 0.012
    assert summary.key_parameters["total_gate_charge_qg"] == 3.75e-08


def test_summary_carries_the_gate_driver_key_parameters(repo) -> None:
    _seed(repo)
    rows, _ = repo.list_parts(SearchFilter(mpn_contains="IR2110"))
    assert len(rows) == 1
    key_parameters = rows[0].key_parameters
    assert key_parameters["supply_voltage_min"] == 4.5
    assert key_parameters["supply_voltage_max"] == 20.0
    assert key_parameters["peak_source_current"] == 2.0
    assert key_parameters["propagation_delay"] == 2e-07


def test_summary_carries_the_offer_numbers(repo) -> None:
    _seed(repo)
    repo.add_offer("m1", {"distributor": "digikey", "sku": "1", "stock": 100})
    repo.add_offer("m1", {"distributor": "mouser", "sku": "2", "stock": 50})
    rows, _ = repo.list_parts(SearchFilter(mpn_contains="IRF3205S"))
    assert rows[0].offers_count == 2
    assert rows[0].total_stock == 150


def test_rejected_values_do_not_match_a_constraint(repo) -> None:
    _seed(repo)
    from shared.schemas import ValueStatus

    repo.add_part(
        make_part(
            part_id="m4",
            mpn="REJECTED1",
            manufacturer="Someone",
            parameters=[
                make_value("vds_max", 10.0, "V", status=ValueStatus.REJECTED),
            ],
        )
    )
    filt = SearchFilter(
        parameters=[ParameterConstraint(name="vds_max", operator="lte", max=100.0, unit="V")]
    )
    rows, total = repo.list_parts(filt)
    assert "REJECTED1" not in _mpns(rows)
    assert total == 3

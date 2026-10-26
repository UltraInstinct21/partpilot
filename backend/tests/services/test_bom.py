"""BOM service tests (FR-14)."""

from __future__ import annotations

from services.bom import BomService
from shared.schemas import Family, LifecycleStatus, Offer, RiskSeverity
from tests.services.fakes import FakePartsRepository, make_part

MANUFACTURER = "Test Manufacturer"


def _offer(distributor: str, stock: int) -> Offer:
    return Offer(distributor=distributor, stock=stock, unit_price=1.0, currency="USD")


def _repository() -> FakePartsRepository:
    parts = [
        make_part(
            "p-obsolete",
            "OBS-1",
            lifecycle=LifecycleStatus.OBSOLETE,
            parameters={"vds_max": 100.0},
            offers=[_offer("digikey", 9000), _offer("mouser", 9000)],
        ),
        make_part(
            "p-nrnd",
            "NRND-1",
            lifecycle=LifecycleStatus.NRND,
            parameters={"vds_max": 100.0},
            offers=[_offer("digikey", 9000), _offer("mouser", 9000)],
        ),
        make_part(
            "p-good",
            "GOOD-1",
            parameters={"vds_max": 100.0},
            offers=[_offer("digikey", 9000), _offer("mouser", 9000)],
        ),
        make_part(
            "p-unknown-lifecycle",
            "UNK-1",
            lifecycle=LifecycleStatus.UNKNOWN,
            parameters={"vds_max": 100.0},
            offers=[_offer("digikey", 9000), _offer("mouser", 9000)],
        ),
        make_part(
            "p-low-stock",
            "LOW-1",
            parameters={"vds_max": 100.0},
            offers=[_offer("digikey", 100), _offer("mouser", 50)],
        ),
        make_part(
            "p-single-source",
            "SINGLE-1",
            parameters={"vds_max": 100.0},
            offers=[_offer("digikey", 9000)],
        ),
    ]
    return FakePartsRepository(parts)


def _csv() -> str:
    return (
        "mpn,qty,manufacturer,reference\n"
        "OBS-1,10,Test Manufacturer,R1\n"
        "NRND-1,5,Test Manufacturer,R2\n"
        "UNKNOWN-99,1,Test Manufacturer,R3\n"
        "GOOD-1,2,Test Manufacturer,R4\n"
    )


def test_the_risks_and_the_counts_are_right() -> None:
    service = BomService(_repository())

    response = service.check_csv(_csv(), filename="bom.csv")

    assert response.filename == "bom.csv"
    assert response.total_lines == 4
    assert response.matched_lines == 3
    assert response.unmatched_lines == 1
    codes = [risk.code for risk in response.risks]
    assert codes == ["obsolete", "nrnd", "not_found"]
    assert response.risk_count == 3
    assert response.highest_severity == RiskSeverity.CRITICAL


def test_every_line_is_returned_with_its_risks() -> None:
    service = BomService(_repository())

    response = service.check_csv(_csv())

    assert [line.mpn for line in response.lines] == [
        "OBS-1",
        "NRND-1",
        "UNKNOWN-99",
        "GOOD-1",
    ]
    assert response.lines[0].risks[0].code == "obsolete"
    assert response.lines[0].risks[0].severity == RiskSeverity.CRITICAL
    assert response.lines[1].risks[0].code == "nrnd"
    assert response.lines[1].risks[0].severity == RiskSeverity.MEDIUM
    assert response.lines[2].risks[0].code == "not_found"
    assert response.lines[2].risks[0].severity == RiskSeverity.HIGH
    assert response.lines[3].risks == []
    assert response.lines[3].matched is True
    assert response.lines[2].matched is False


def test_the_quantity_and_the_reference_are_read() -> None:
    service = BomService(_repository())

    response = service.check_csv(_csv())

    assert response.lines[0].quantity == 10
    assert response.lines[0].reference == "R1"
    assert response.lines[0].manufacturer == "Test Manufacturer"


def test_an_empty_csv_returns_an_empty_result() -> None:
    service = BomService(_repository())

    response = service.check_csv("")

    assert response.total_lines == 0
    assert response.risks == []
    assert response.highest_severity is None


def test_a_semicolon_delimiter_is_detected() -> None:
    service = BomService(_repository())
    content = "mpn;qty;manufacturer\nOBS-1;10;Test Manufacturer\nGOOD-1;2;Test Manufacturer\n"

    response = service.check_csv(content)

    assert response.total_lines == 2
    assert response.matched_lines == 2
    assert [risk.code for risk in response.risks] == ["obsolete"]


def test_a_tab_delimiter_is_detected() -> None:
    service = BomService(_repository())
    content = "mpn\tqty\tmanufacturer\nOBS-1\t10\tTest Manufacturer\n"

    response = service.check_csv(content)

    assert response.total_lines == 1
    assert response.lines[0].quantity == 10


def test_a_csv_without_a_header_is_read_as_data() -> None:
    service = BomService(_repository())
    content = "OBS-1\nGOOD-1\n"

    response = service.check_csv(content)

    assert response.total_lines == 2
    assert response.matched_lines == 2
    assert [risk.code for risk in response.risks] == ["obsolete"]


def test_a_header_with_another_name_is_still_understood() -> None:
    service = BomService(_repository())
    content = "Manufacturer Part Number,Quantity,Manufacturer\nOBS-1,1,Test Manufacturer\n"

    response = service.check_csv(content)

    assert response.total_lines == 1
    assert response.lines[0].mpn == "OBS-1"
    assert response.lines[0].quantity == 1


def test_a_row_with_too_few_cells_does_not_raise() -> None:
    service = BomService(_repository())
    content = "mpn,qty,manufacturer,reference\nOBS-1,3\n"

    response = service.check_csv(content)

    assert response.total_lines == 1
    assert response.lines[0].mpn == "OBS-1"
    assert response.lines[0].quantity == 3


def test_a_broken_csv_does_not_raise() -> None:
    service = BomService(_repository())
    content = 'mpn,qty\n"OBS-1,10,broken\n'

    response = service.check_csv(content)

    assert response.total_lines >= 1


def test_a_manufacturer_mismatch_is_a_risk() -> None:
    service = BomService(_repository())
    content = "mpn,qty,manufacturer\nGOOD-1,1,Another Company\n"

    response = service.check_csv(content)

    codes = [risk.code for risk in response.risks]
    assert "manufacturer_mismatch" in codes
    mismatch = next(risk for risk in response.risks if risk.code == "manufacturer_mismatch")
    assert mismatch.severity == RiskSeverity.MEDIUM


def test_a_short_manufacturer_name_is_not_a_mismatch() -> None:
    service = BomService(_repository())
    content = "mpn,qty,manufacturer\nGOOD-1,1,Test\n"

    response = service.check_csv(content)

    assert [risk.code for risk in response.risks] == []


def test_low_stock_is_a_risk() -> None:
    service = BomService(_repository())
    content = "mpn,qty,manufacturer\nLOW-1,1,Test Manufacturer\n"

    response = service.check_csv(content)

    codes = [risk.code for risk in response.risks]
    assert "low_stock" in codes
    low = next(risk for risk in response.risks if risk.code == "low_stock")
    assert low.severity == RiskSeverity.MEDIUM


def test_single_source_is_a_risk() -> None:
    service = BomService(_repository())
    content = "mpn,qty,manufacturer\nSINGLE-1,1,Test Manufacturer\n"

    response = service.check_csv(content)

    codes = [risk.code for risk in response.risks]
    assert "single_source" in codes
    single = next(risk for risk in response.risks if risk.code == "single_source")
    assert single.severity == RiskSeverity.LOW


def test_an_unknown_lifecycle_is_a_risk() -> None:
    service = BomService(_repository())
    content = "mpn,qty,manufacturer\nUNK-1,1,Test Manufacturer\n"

    response = service.check_csv(content)

    codes = [risk.code for risk in response.risks]
    assert "unknown_lifecycle" in codes


def test_the_stock_threshold_is_configurable() -> None:
    service = BomService(_repository(), low_stock_threshold=100_000)
    content = "mpn,qty,manufacturer\nGOOD-1,1,Test Manufacturer\n"

    response = service.check_csv(content)

    assert "low_stock" in [risk.code for risk in response.risks]


def test_a_part_is_matched_by_a_fuzzy_mpn_when_the_exact_match_fails() -> None:
    service = BomService(_repository())
    content = "mpn,qty,manufacturer\nOBS,1,Test Manufacturer\n"

    response = service.check_csv(content)

    assert response.matched_lines == 1
    assert response.lines[0].matched_part_id == "p-obsolete"


def test_the_took_ms_is_set() -> None:
    service = BomService(_repository())

    response = service.check_csv(_csv())

    assert response.took_ms >= 0


def test_a_gate_driver_part_is_checked_the_same_way() -> None:
    parts = [
        make_part(
            "p-driver",
            "DRV-1",
            family=Family.GATE_DRIVER,
            lifecycle=LifecycleStatus.OBSOLETE,
            parameters={"supply_voltage_max": 20.0},
            offers=[_offer("digikey", 9000), _offer("mouser", 9000)],
        )
    ]
    service = BomService(FakePartsRepository(parts))
    content = "mpn,qty,manufacturer\nDRV-1,1,Test Manufacturer\n"

    response = service.check_csv(content)

    assert response.total_lines == 1
    assert response.risks[0].code == "obsolete"


def test_packaging_suffix_matching() -> None:
    service = BomService(_repository())
    content = "mpn,qty\nGOOD-1-TR,5\nGOOD-1-PBF,2\n"

    response = service.check_csv(content)

    assert response.total_lines == 2
    assert response.matched_lines == 2
    assert response.lines[0].matched_part_id == "p-good"
    assert response.lines[1].matched_part_id == "p-good"


def test_eda_preamble_and_comments_are_skipped() -> None:
    service = BomService(_repository())
    content = (
        "# KiCad Version 8.0 BOM Export\n"
        "# Project: Motor Controller Inverter\n"
        "Designator;Quantity;Manufacturer Part Number;Comment\n"
        "Q1;2;GOOD-1;Power MOSFET\n"
        "Q2;1;OBS-1;Gate Switch\n"
    )

    response = service.check_csv(content)

    assert response.total_lines == 2
    assert response.matched_lines == 2
    assert response.lines[0].mpn == "GOOD-1"
    assert response.lines[0].quantity == 2
    assert response.lines[0].reference == "Q1"
    assert response.lines[1].mpn == "OBS-1"


def test_bom_live_discovery_at_scale() -> None:
    class FakeAdvisor:
        def __init__(self, repo):
            self.repo = repo
            self.discovered = []

        def discover_and_ingest(self, mpn):
            self.discovered.append(mpn)
            part = make_part(
                f"discovered-{mpn.lower()}",
                mpn,
                lifecycle=LifecycleStatus.ACTIVE,
                offers=[_offer("digikey", 5000)],
            )
            self.repo.add_part(part)
            return [part]

    repo = _repository()
    advisor = FakeAdvisor(repo)
    service = BomService(repo, advisor=advisor)

    content = "MPN,Qty,Reference\nSTM32F401CCU6,5,U1\nESP32-WROOM-32E,2,U2\nOPA2134PA,1,U3\n"
    response = service.check_csv(content)

    assert response.total_lines == 3
    assert response.matched_lines == 3
    assert "STM32F401CCU6" in advisor.discovered
    assert "ESP32-WROOM-32E" in advisor.discovered
    assert "OPA2134PA" in advisor.discovered
    assert response.unmatched_lines == 0


def test_item_column_does_not_override_component_mpn() -> None:
    parts = [
        make_part("p-good", "BSC030N08NS5", offers=[_offer("digikey", 5000), _offer("mouser", 5000)]),
    ]
    service = BomService(FakePartsRepository(parts))
    content = "Item,Component,Qty,Designator\n1,BSC030N08NS5,4,Q1-Q4\n"

    response = service.check_csv(content)

    assert response.total_lines == 1
    assert response.matched_lines == 1
    assert response.lines[0].mpn == "BSC030N08NS5"
    assert response.lines[0].quantity == 4
    assert response.lines[0].reference == "Q1-Q4"



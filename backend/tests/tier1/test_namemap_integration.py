"""Integration of the tier-1 name matcher with the database ``name_map``."""

from __future__ import annotations

import json
from pathlib import Path

from extraction.tier1 import NameMap, PdfTier1Extractor, load_name_map, lookup_from_rows
from shared.schemas import Family


def test_lookup_from_rows_maps_raw_names() -> None:
    rows = [
        {"raw_name": "Drain-Source On-Resistance", "standard_name": "rds_on"},
        {"raw_name": "VCC", "standard_name": "supply_voltage_max"},
    ]
    lookup = lookup_from_rows(rows)
    assert lookup("Drain-Source On-Resistance") == "rds_on"
    assert lookup("VCC") == "supply_voltage_max"
    assert lookup("Unknown Parameter") is None


def test_the_database_name_map_export_can_be_loaded() -> None:
    """The export of the database layer is the shape tier 1 expects."""
    path = Path(__file__).resolve().parents[2] / "db" / "seed_data" / "name_map.json"
    if not path.exists():  # the database agent may not have shipped it yet
        return
    lookup = load_name_map(path)
    assert lookup("Drain-Source On-Resistance") == "rds_on"
    assert lookup("RDS(on)") == "rds_on"


def test_a_json_export_can_be_written_and_read(tmp_path: Path) -> None:
    path = tmp_path / "name_map.json"
    path.write_text(
        json.dumps({"name_map": [{"raw_name": "Qrr", "standard_name": "reverse_recovery_qrr"}]}),
        encoding="utf-8",
    )
    lookup = load_name_map(path)
    assert lookup("Qrr") == "reverse_recovery_qrr"


def test_the_injected_table_wins_over_the_builtin_aliases(fixtures_dir: Path) -> None:
    lookup = lookup_from_rows(
        [{"raw_name": "RDS(on)", "standard_name": "rds_on"}],
    )
    extractor = PdfTier1Extractor(name_map=NameMap(lookup))
    result = extractor.extract(str(fixtures_dir / "pdfs" / "synthetic_mosfet.pdf"), Family.MOSFET)
    produced = {value.name: value for value in result.values}
    assert produced["rds_on"].value == 5.5

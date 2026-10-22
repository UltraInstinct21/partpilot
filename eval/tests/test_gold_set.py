"""Tests for the gold set loader, validator and agreement report."""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.gold_set import (
    GOLD_SET_COLUMNS,
    GoldSetError,
    agreement_rate,
    inter_annotator_agreement,
    load_gold_set,
    validate_gold_set,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE = REPO_ROOT / "eval" / "gold_set_template.csv"
EXAMPLE = REPO_ROOT / "contracts" / "fixtures" / "gold" / "gold_set_example.csv"

HEADER = ",".join(GOLD_SET_COLUMNS)


def write_csv(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "gold.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_template_is_valid() -> None:
    assert validate_gold_set(TEMPLATE) == []


def test_the_template_has_the_documented_header() -> None:
    header = TEMPLATE.read_text(encoding="utf-8").splitlines()[0]
    assert header == HEADER


def test_the_template_has_three_example_rows() -> None:
    lines = [line for line in TEMPLATE.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 4


def test_the_recorded_example_fixture_is_valid() -> None:
    assert validate_gold_set(EXAMPLE) == []


def test_the_validator_reports_a_missing_column(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "part_id,mpn,value\np1,MPN,1.0\n")
    problems = validate_gold_set(path)
    assert any("missing the column" in problem for problem in problems)


def test_the_validator_reports_a_value_that_is_not_a_number(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        f"{HEADER}\np1,MPN,TI,mosfet,vds_max,abc,V,{{}},member-d,,,\n",
    )
    problems = validate_gold_set(path)
    assert any("not numeric" in problem for problem in problems)


def test_the_validator_reports_a_missing_unit(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        f"{HEADER}\np1,MPN,TI,mosfet,vds_max,12.0,,{{}},member-d,,,\n",
    )
    problems = validate_gold_set(path)
    assert any("unit is missing" in problem for problem in problems)


def test_the_validator_reports_a_duplicate_pair(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        f"{HEADER}\n"
        "p1,MPN,TI,mosfet,vds_max,12.0,V,{},member-d,,,\n"
        "p1,MPN,TI,mosfet,vds_max,13.0,V,{},member-d,,,\n",
    )
    problems = validate_gold_set(path)
    assert any("already used" in problem for problem in problems)


def test_the_validator_reports_a_row_without_a_labeller(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        f"{HEADER}\np1,MPN,TI,mosfet,vds_max,12.0,V,{{}},,,,\n",
    )
    problems = validate_gold_set(path)
    assert any("labelled_by is empty" in problem for problem in problems)


def test_the_validator_reports_a_wrong_agreement_value(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        f"{HEADER}\np1,MPN,TI,mosfet,vds_max,12.0,V,{{}},member-d,member-c,maybe,\n",
    )
    problems = validate_gold_set(path)
    assert any("agreement" in problem for problem in problems)


def test_the_validator_reports_a_missing_file() -> None:
    problems = validate_gold_set("/tmp/does-not-exist-partpilot.csv")
    assert problems and "does not exist" in problems[0]


def test_load_gold_set_reads_the_rows(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        f"{HEADER}\n" "p1,MPN,TI,mosfet,vds_max,12.0,V,{{}},member-d,member-c,yes,the note\n",
    )
    rows = load_gold_set(path)
    assert len(rows) == 1
    row = rows[0]
    assert row.part_id == "p1"
    assert row.value == pytest.approx(12.0)
    assert row.unit == "V"
    assert row.labelled_by == "member-d"
    assert row.second_check_by == "member-c"
    assert row.agreement == "yes"
    assert row.notes == "the note"
    assert row.double_checked is True


def test_load_gold_set_parses_the_condition(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        f"{HEADER}\n" 'p1,MPN,TI,mosfet,rds_on,12.0,mohm,"{""Id"": ""2 A""}",member-d,,,\n',
    )
    rows = load_gold_set(path)
    assert rows[0].condition == {"Id": "2 A"}


def test_load_gold_set_raises_on_a_broken_file(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        f"{HEADER}\np1,MPN,TI,mosfet,vds_max,abc,V,{{}},member-d,,,\n",
    )
    with pytest.raises(GoldSetError):
        load_gold_set(path)


def test_load_gold_set_can_skip_the_broken_rows(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        f"{HEADER}\n"
        "p1,MPN,TI,mosfet,vds_max,abc,V,{},member-d,,,\n"
        "p2,MPN,TI,mosfet,vds_max,12.0,V,{},member-d,,,\n",
    )
    rows = load_gold_set(path, skip_invalid=True)
    assert [row.part_id for row in rows] == ["p2"]


def test_inter_annotator_agreement_counts_the_checked_rows(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        f"{HEADER}\n"
        "p1,MPN,TI,mosfet,vds_max,12.0,V,{},member-d,member-c,yes,\n"
        "p2,MPN,TI,mosfet,vds_max,13.0,V,{},member-d,member-c,no,\n"
        "p3,MPN,TI,mosfet,vds_max,14.0,V,{},member-d,member-c,yes,\n"
        "p4,MPN,TI,mosfet,vds_max,15.0,V,{},member-d,,,\n",
    )
    rows = load_gold_set(path)
    report = inter_annotator_agreement(rows)
    assert report["total_rows"] == 4
    assert report["double_checked"] == 3
    assert report["double_checked_pct"] == pytest.approx(0.75)
    assert report["agreed"] == 2
    assert report["disagreed"] == 1
    assert report["agreement_rate"] == pytest.approx(2 / 3)
    assert agreement_rate(rows) == pytest.approx(2 / 3)


def test_inter_annotator_agreement_of_an_unchecked_set_is_zero() -> None:
    report = inter_annotator_agreement([])
    assert report["total_rows"] == 0
    assert report["agreement_rate"] == 0.0

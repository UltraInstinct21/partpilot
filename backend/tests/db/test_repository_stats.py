"""``stats()`` - the dashboard numbers."""

from __future__ import annotations

from datetime import UTC, datetime

from shared.schemas import LLMCallRecord, SourceRef, SourceType, ValueStatus
from tests.db.conftest import make_part, make_value


def test_stats_of_an_empty_database(repo) -> None:
    stats = repo.stats()
    assert stats.parts_total == 0
    assert stats.parameters_total == 0
    assert stats.sources_total == 0
    assert stats.review_pending == 0
    assert stats.coverage_pct == 0.0
    assert stats.mean_confidence == 0.0
    assert stats.llm_calls_total == 0
    assert stats.avg_cost_per_datasheet == 0.0


def test_stats_counts_the_parts_and_the_values(repo) -> None:
    repo.add_part(
        make_part(
            part_id="p1",
            mpn="IRF3205S",
            manufacturer="International Rectifier",
            parameters=[
                make_value("vds_max", 56.0, "V", confidence=0.9, status=ValueStatus.ACCEPTED),
                make_value("rds_on", 0.012, "ohm", confidence=0.5, status=ValueStatus.REVIEW),
            ],
        )
    )
    repo.add_part(
        make_part(
            part_id="p2",
            mpn="IR2110",
            manufacturer="International Rectifier",
            family="gate_driver",
            parameters=[
                make_value(
                    "supply_voltage_max", 20.0, "V", confidence=0.8, status=ValueStatus.ACCEPTED
                ),
            ],
        )
    )
    stats = repo.stats()
    assert stats.parts_total == 2
    assert stats.parts_by_family == {"mosfet": 1, "gate_driver": 1}
    assert stats.parts_by_lifecycle == {"active": 2}
    assert stats.parts_by_manufacturer == {"International Rectifier": 2}
    assert stats.parameters_total == 3
    assert stats.values_by_status == {"accepted": 2, "review": 1}
    assert stats.values_by_method == {"tier1": 3}
    assert stats.review_pending == 1
    assert stats.coverage_pct == 100.0
    assert stats.mean_confidence == round((0.9 + 0.5 + 0.8) / 3, 6)


def test_stats_counts_the_pending_reviews(repo) -> None:
    repo.add_part(
        make_part(
            parameters=[
                make_value("vds_max", 56.0, "V", confidence=0.4, status=ValueStatus.REVIEW),
            ]
        )
    )
    stats = repo.stats()
    assert stats.review_pending == 1
    assert stats.values_by_status == {"review": 1}
    assert stats.coverage_pct == 0.0


def test_record_llm_call_shows_up_in_the_stats(repo) -> None:
    repo.add_source(
        SourceRef(source_id="pdf-1", url="https://example.invalid/a.pdf", type=SourceType.PDF)
    )
    repo.record_llm_call(
        LLMCallRecord(
            call_id="call-1",
            chain="tier2",
            model="gpt-4o-mini",
            tokens_in=1000,
            tokens_out=500,
            cost=0.0025,
            prompt_version="v1",
            part_id="p1",
        )
    )
    repo.record_llm_call(
        LLMCallRecord(
            chain="tier3",
            model="gpt-4o-mini",
            tokens_in=2000,
            tokens_out=1000,
            cost=0.005,
            cached=True,
            duration_ms=1234,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    stats = repo.stats()
    assert stats.llm_calls_total == 2
    assert stats.llm_tokens_in == 3000
    assert stats.llm_tokens_out == 1500
    assert stats.llm_cost_total == 0.0075
    # one PDF source -> the cost per datasheet
    assert stats.avg_cost_per_datasheet == 0.0075

    repo.add_source(
        SourceRef(source_id="pdf-2", url="https://example.invalid/b.pdf", type=SourceType.PDF)
    )
    stats = repo.stats()
    assert stats.avg_cost_per_datasheet == 0.00375


def test_stats_counts_the_sources(repo) -> None:
    repo.add_source(
        SourceRef(source_id="api-1", url="https://example.invalid/api", type=SourceType.API)
    )
    stats = repo.stats()
    assert stats.sources_total == 1

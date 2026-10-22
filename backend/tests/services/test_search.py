"""Search service tests (FR-11, NFR-04)."""

from __future__ import annotations

from services.search import SearchService, describe_filter
from shared.schemas import Family, ParameterConstraint, SearchFilter
from tests.services.fakes import FakeLLMExtractor, FakePartsRepository

# Every MOSFET of the seed data with an Rds(on) of at most 10 mohm.
LOW_RDS_MPNS = {
    "BSC030N08NS5",
    "Si7148DP",
    "NVMFS5C430NL",
    "PSMN2R30",
    "STP55NF06L",
    "CSD1642Q5",
    "DMN3024U-13",
    "AOD4184A",
    "CSD19536Y",
}


def _low_rds_filter() -> SearchFilter:
    return SearchFilter(
        family=Family.MOSFET,
        parameters=[
            ParameterConstraint(name="rds_on", operator="lte", max=10.0, unit="mohm"),
        ],
    )


def test_query_is_mapped_to_a_filter_and_executed() -> None:
    repo = FakePartsRepository()
    llm = FakeLLMExtractor({"low rds": _low_rds_filter()})
    service = SearchService(repo, llm)

    response = service.search("low rds", limit=50)

    assert llm.call_counts["build_search_filter"] == 1
    assert response.llm_used is True
    assert response.filter == _low_rds_filter()
    assert {part.mpn for part in response.results} == LOW_RDS_MPNS
    assert response.total == len(LOW_RDS_MPNS)
    assert all(part.family == Family.MOSFET for part in response.results)


def test_the_repository_executes_the_filter_not_the_llm() -> None:
    repo = FakePartsRepository()
    llm = FakeLLMExtractor({"low rds": _low_rds_filter()})
    service = SearchService(repo, llm)

    service.search("low rds")

    calls = repo.calls_to("list_parts")
    assert len(calls) == 1
    executed = repo.last_filter()
    assert executed is not None
    assert executed.family == Family.MOSFET
    assert [constraint.name for constraint in executed.parameters] == ["rds_on"]
    # The LLM never returned any row.
    assert all(call[0] != "results" for call in repo.calls)


def test_an_edited_filter_runs_without_the_llm() -> None:
    repo = FakePartsRepository()
    llm = FakeLLMExtractor({"low rds": _low_rds_filter()})
    service = SearchService(repo, llm)

    response = service.search_filter(_low_rds_filter())

    assert llm.call_counts["build_search_filter"] == 0
    assert response.llm_used is False
    assert {part.mpn for part in response.results} == LOW_RDS_MPNS
    assert repo.last_filter() == _low_rds_filter()


def test_an_unknown_parameter_constraint_is_dropped() -> None:
    repo = FakePartsRepository()
    bad_filter = SearchFilter(
        family=Family.MOSFET,
        parameters=[
            ParameterConstraint(name="rds_on", operator="lte", max=10.0, unit="mohm"),
            ParameterConstraint(name="banana_power", operator="lte", max=3.0),
        ],
    )
    llm = FakeLLMExtractor({"weird": bad_filter})
    service = SearchService(repo, llm)

    response = service.search("weird")

    assert [constraint.name for constraint in response.filter.parameters] == ["rds_on"]
    assert repo.last_filter() is not None
    assert [constraint.name for constraint in repo.last_filter().parameters] == ["rds_on"]
    assert response.total == len(LOW_RDS_MPNS)


def test_an_impossible_constraint_is_repaired_not_dropped() -> None:
    repo = FakePartsRepository()
    bad_filter = SearchFilter(
        family=Family.MOSFET,
        parameters=[
            ParameterConstraint(name="vds_max", operator="between", min=100.0, max=10.0, unit="V"),
        ],
    )
    service = SearchService(repo, FakeLLMExtractor({"odd": bad_filter}))

    response = service.search("odd")

    constraint = response.filter.parameters[0]
    assert constraint.min == 10.0
    assert constraint.max == 100.0


def test_limit_and_offset_are_honoured() -> None:
    repo = FakePartsRepository()
    service = SearchService(repo, FakeLLMExtractor({"low rds": _low_rds_filter()}))

    first = service.search("low rds", limit=3)
    second = service.search("low rds", limit=3, offset=3)

    assert len(first.results) == 3
    assert first.total == len(LOW_RDS_MPNS)
    assert len(second.results) == 3
    assert {part.mpn for part in first.results}.isdisjoint({part.mpn for part in second.results})


def test_the_total_is_the_unpaginated_count() -> None:
    repo = FakePartsRepository()
    service = SearchService(repo, FakeLLMExtractor({"low rds": _low_rds_filter()}))

    response = service.search("low rds", limit=2)

    assert len(response.results) == 2
    assert response.total == len(LOW_RDS_MPNS)


def test_took_ms_and_the_explanation_are_filled_in() -> None:
    repo = FakePartsRepository()
    service = SearchService(repo, FakeLLMExtractor({"low rds": _low_rds_filter()}))

    response = service.search("low rds")

    assert response.took_ms >= 0
    assert response.filter_explanation
    assert "rds_on" in response.filter_explanation


def test_a_broken_llm_still_returns_results() -> None:
    repo = FakePartsRepository()
    llm = FakeLLMExtractor(raise_on_filter=True)
    service = SearchService(repo, llm)

    response = service.search("anything")

    assert response.llm_used is False
    assert response.filter == SearchFilter()
    assert response.total == 30
    assert len(response.results) == 30


def test_a_service_without_an_llm_falls_back_to_the_rule_based_filter() -> None:
    repo = FakePartsRepository()
    service = SearchService(repo)

    response = service.search("mosfet")

    assert response.llm_used is False
    # The deterministic fallback still recognises the family.
    assert response.filter.family is Family.MOSFET
    assert response.total == 15


def test_the_fallback_builds_a_filter_without_a_model() -> None:
    repo = FakePartsRepository()
    service = SearchService(repo)

    response = service.search("100 V N-channel MOSFET, Rds(on) below 5 mOhm, in stock")

    assert response.llm_used is False
    constraints = {c.name: c for c in response.filter.parameters}
    assert "rds_on" in constraints
    assert constraints["rds_on"].unit == "mohm"
    assert constraints["rds_on"].max == 5.0
    assert response.filter.family is Family.MOSFET
    assert response.filter.in_stock is True


def test_a_broken_llm_falls_back_to_the_rule_based_filter() -> None:
    class BrokenLLM:
        def build_search_filter(self, query: str):
            raise RuntimeError("the provider is down")

    repo = FakePartsRepository()
    service = SearchService(repo, BrokenLLM())

    response = service.search("mosfet")

    assert response.llm_used is False
    assert response.filter.family is Family.MOSFET
    assert response.total == 15


def test_the_fallback_never_guesses_an_unknown_constraint() -> None:
    from services.search import fallback_filter

    filt = fallback_filter("a part with a very strange property of 42")
    assert filt.parameters == []


def test_a_slow_model_does_not_hold_the_request() -> None:
    """NFR-04: a search answers in 5 seconds or less."""
    import time

    class SlowLLM:
        def build_search_filter(self, query: str):
            time.sleep(5)
            raise AssertionError("the model must not be waited for")

    repo = FakePartsRepository()
    service = SearchService(repo, SlowLLM(), llm_budget_seconds=0.2)

    started = time.perf_counter()
    response = service.search("mosfet")
    elapsed = time.perf_counter() - started

    assert elapsed < 3.0, f"the search waited {elapsed:.1f} s for the model"
    assert response.llm_used is False
    assert response.filter.family is Family.MOSFET


def test_the_pagination_is_clamped() -> None:
    repo = FakePartsRepository()
    service = SearchService(repo, max_limit=25, max_offset=100)

    response = service.search_filter(SearchFilter(), limit=5000, offset=-10)

    assert response.limit == 25
    assert response.offset == 0


def test_describe_filter_reads_like_a_sentence() -> None:
    filt = SearchFilter(
        family=Family.MOSFET,
        parameters=[
            ParameterConstraint(name="vds_max", operator="lte", max=100.0, unit="V"),
            ParameterConstraint(name="rds_on", operator="lte", max=5.0, unit="mohm"),
        ],
    )

    assert describe_filter(filt) == "MOSFET, vds_max <= 100 V, rds_on <= 5 mohm"
    assert describe_filter(SearchFilter()) == "all parts"


def test_the_llm_cannot_choose_the_rows() -> None:
    repo = FakePartsRepository()
    llm = FakeLLMExtractor({"one part": SearchFilter(mpn_contains="IRF3205S")})
    service = SearchService(repo, llm)

    response = service.search("one part")

    assert [part.mpn for part in response.results] == ["IRF3205S"]
    assert response.total == 1


def test_the_family_filter_is_applied_by_the_repository() -> None:
    repo = FakePartsRepository()
    service = SearchService(repo, FakeLLMExtractor())

    response = service.search_filter(SearchFilter(family=Family.GATE_DRIVER))

    assert response.total == 15
    assert all(part.family == Family.GATE_DRIVER for part in response.results)


def test_search_filter_also_drops_an_unknown_parameter() -> None:
    repo = FakePartsRepository()
    service = SearchService(repo)

    response = service.search_filter(
        SearchFilter(parameters=[ParameterConstraint(name="not_a_parameter", max=1.0)])
    )

    assert response.filter.parameters == []
    assert response.total == 30

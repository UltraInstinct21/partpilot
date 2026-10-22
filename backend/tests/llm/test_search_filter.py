"""The filter builder builds a filter, the database executes it."""

from __future__ import annotations

from extraction.llm import LLMExtractorImpl
from shared.schemas import Family, SearchFilter

from .conftest import make_tool_model

FILTER_PAYLOAD = {
    "family": "mosfet",
    "manufacturer": "Infineon",
    "manufacturer_in": [],
    "mpn_contains": None,
    "package": None,
    "package_in": [],
    "lifecycle_status": [],
    "in_stock": True,
    "parameters": [
        {
            "name": "rds_on",
            "unit": "mOhm",
            "min": None,
            "max": 50.0,
            "typ": None,
            "operator": "lte",
        },
        {
            "name": "quantum_flux",
            "unit": "W",
            "min": None,
            "max": 1.0,
            "typ": None,
            "operator": "lte",
        },
    ],
    "text": "infineon mosfets with low rds on",
}


def _extractor(model, recorder, settings):
    return LLMExtractorImpl(model=model, recorder=recorder, settings=settings)


def test_a_valid_filter_is_returned(settings, recorder) -> None:
    model = make_tool_model(FILTER_PAYLOAD, "SearchFilter")
    extractor = _extractor(model, recorder, settings)

    filt = extractor.build_search_filter("infineon mosfets with rds(on) below 50 mOhm")

    assert isinstance(filt, SearchFilter)
    assert filt.family == Family.MOSFET
    assert filt.manufacturer == "Infineon"
    assert filt.in_stock is True
    assert len(recorder.records) == 1
    assert recorder.last.chain == "search_filter"
    assert recorder.last.prompt_version == "v1"


def test_an_unknown_parameter_is_dropped(settings, recorder) -> None:
    model = make_tool_model(FILTER_PAYLOAD, "SearchFilter")
    extractor = _extractor(model, recorder, settings)

    filt = extractor.build_search_filter("infineon mosfets")

    names = [constraint.name for constraint in filt.parameters]
    assert names == ["rds_on"]
    assert "quantum_flux" not in names


def test_a_broken_filter_keeps_the_query_as_text(settings, recorder) -> None:
    model = make_tool_model({"family": "not_a_family"}, "SearchFilter")
    extractor = _extractor(model, recorder, settings)

    filt = extractor.build_search_filter("anything")

    assert isinstance(filt, SearchFilter)
    assert filt.text == "anything"
    assert filt.parameters == []

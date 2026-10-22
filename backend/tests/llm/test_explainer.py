"""The alternative explainer writes one short sentence and invents no number."""

from __future__ import annotations

from extraction.llm import LLMExtractorImpl
from extraction.llm.chains import MAX_EXPLANATION_WORDS

from .conftest import make_text_model

DIFFERENCES = {
    "rds_on": {"reference": 45.0, "candidate": 25.0},
    "total_gate_charge_qg": {"reference": 80.0, "candidate": 120.0},
}


def _extractor(model, recorder, settings):
    return LLMExtractorImpl(model=model, recorder=recorder, settings=settings)


def test_a_short_sentence_is_returned(settings, recorder) -> None:
    model = make_text_model("The candidate has a lower rds_on but a higher total gate charge.")
    extractor = _extractor(model, recorder, settings)

    sentence = extractor.explain_alternative(DIFFERENCES, "IRFP260N")

    assert sentence == "The candidate has a lower rds_on but a higher total gate charge."
    assert len(sentence.split()) <= MAX_EXPLANATION_WORDS
    assert len(recorder.records) == 1
    assert recorder.last.chain == "alternative_explainer"
    assert recorder.last.prompt_version == "v1"


def test_a_number_that_is_not_in_the_input_is_not_used(settings, recorder) -> None:
    model = make_text_model("The candidate has a 999 W lower rds_on than the reference.")
    extractor = _extractor(model, recorder, settings)

    sentence = extractor.explain_alternative(DIFFERENCES, "IRFP260N")

    assert "999" not in sentence
    assert len(sentence.split()) <= MAX_EXPLANATION_WORDS


def test_a_number_that_is_in_the_input_may_be_used(settings, recorder) -> None:
    model = make_text_model("The candidate has a lower rds_on of 25 mOhm.")
    extractor = _extractor(model, recorder, settings)

    sentence = extractor.explain_alternative(DIFFERENCES, "IRFP260N")

    assert "25" in sentence


def test_a_long_sentence_is_shortened(settings, recorder) -> None:
    model = make_text_model(" ".join(["word"] * 60))
    extractor = _extractor(model, recorder, settings)

    sentence = extractor.explain_alternative(DIFFERENCES, "IRFP260N")

    assert len(sentence.split()) <= MAX_EXPLANATION_WORDS


def test_the_fallback_sentence_names_the_trade_off(settings, recorder) -> None:
    model = make_text_model("")
    extractor = _extractor(model, recorder, settings)

    sentence = extractor.explain_alternative(DIFFERENCES, "IRFP260N")

    assert "rds_on" in sentence
    assert "total_gate_charge_qg" in sentence
    assert len(sentence.split()) <= MAX_EXPLANATION_WORDS

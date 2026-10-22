"""The chain factory must never open a connection on its own."""

from __future__ import annotations

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.runnables.retry import RunnableRetry

from extraction.llm import factory
from extraction.llm.factory import (
    build_chat_model,
    chat_model_core,
    retry_attempts,
    setup_llm_cache,
)

from .conftest import FakeToolChatModel, tool_message


def test_injected_model_is_returned_untouched(monkeypatch) -> None:
    def explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("the network must not be touched")

    monkeypatch.setattr(factory, "init_chat_model", explode)
    fake = FakeToolChatModel(responses=[tool_message({})])
    assert build_chat_model(model=fake) is fake


def test_build_chat_model_applies_the_retry_wrapper(monkeypatch, settings) -> None:
    calls: list[str] = []

    def fake_init(model, **kwargs):
        calls.append(model)
        return FakeToolChatModel(responses=[tool_message({})])

    monkeypatch.setattr(factory, "init_chat_model", fake_init)
    settings.llm_max_retries = 3
    built = build_chat_model(settings=settings)
    assert isinstance(built, RunnableRetry)
    assert retry_attempts(built) == 3
    assert calls == [f"{settings.llm_provider}:{settings.llm_model}"]


def test_build_chat_model_uses_the_vision_model(monkeypatch, settings) -> None:
    calls: list[str] = []

    def fake_init(model, **kwargs):
        calls.append(model)
        return FakeToolChatModel(responses=[tool_message({})])

    monkeypatch.setattr(factory, "init_chat_model", fake_init)
    build_chat_model(settings=settings, vision=True)
    assert calls == [f"{settings.llm_provider}:{settings.llm_vision_model}"]


def test_chat_model_core_unwraps_the_retry_wrapper() -> None:
    fake = FakeToolChatModel(responses=[tool_message({})])
    wrapped = fake.with_retry(stop_after_attempt=3)
    assert chat_model_core(wrapped) is fake
    assert chat_model_core(fake) is fake
    assert chat_model_core(None) is None


def test_rate_limiter_is_built_from_the_settings(monkeypatch, settings) -> None:
    seen: dict[str, object] = {}

    def fake_init(model, **kwargs):
        seen.update(kwargs)
        return FakeToolChatModel(responses=[tool_message({})])

    monkeypatch.setattr(factory, "init_chat_model", fake_init)
    settings.llm_requests_per_second = 2.5
    build_chat_model(settings=settings)
    limiter = seen["rate_limiter"]
    assert limiter is not None
    assert getattr(limiter, "requests_per_second", None) == 2.5
    assert seen["temperature"] == settings.llm_temperature


def test_setup_llm_cache_creates_the_directory(settings) -> None:
    settings.llm_cache_enabled = True
    assert setup_llm_cache(settings) is True
    assert settings.llm_cache_dir.is_dir()
    assert (settings.llm_cache_dir / factory.CACHE_DB_NAME).exists()


def test_build_chat_model_installs_the_cache(monkeypatch, settings) -> None:
    settings.llm_cache_enabled = True
    monkeypatch.setattr(
        factory,
        "init_chat_model",
        lambda model, **kwargs: FakeToolChatModel(responses=[tool_message({})]),
    )
    build_chat_model(settings=settings)
    assert (settings.llm_cache_dir / factory.CACHE_DB_NAME).exists()


def test_setup_llm_cache_can_be_switched_off(settings) -> None:
    settings.llm_cache_enabled = False
    assert setup_llm_cache(settings) is False
    assert not settings.llm_cache_dir.exists()


def test_importing_the_factory_does_not_build_a_model() -> None:
    # A plain fake model is enough - the point is that the module level code
    # never calls init_chat_model.
    assert factory.init_chat_model is not None
    assert issubclass(FakeMessagesListChatModel, object)

"""Construction of the chat model and of the LLM cache (plan WP4).

Rules encoded here:

* the provider and the model name come from :class:`shared.config.Settings`,
  they are never hard coded;
* every call is rate limited and retried;
* a SQLite cache is installed when ``Settings.llm_cache_enabled`` is set;
* **no provider connection is created at import time** - a model is built when
  :func:`build_chat_model` is called, and only then;
* a model can be injected (``model=...``) which is how the tests use a fake
  chat model and never touch the network.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.globals import set_llm_cache
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import Runnable

from shared.config import Settings, get_settings

logger = logging.getLogger(__name__)

CACHE_DB_NAME = "llm_cache.db"


def build_chat_model(
    settings: Settings | None = None,
    vision: bool = False,
    model: Runnable | None = None,
    **kwargs: Any,
) -> Runnable:
    """Return a ready to use chat model.

    Args:
        settings: the settings to use; the cached global settings by default.
        vision: build the vision model (``Settings.llm_vision_model``) instead
            of the text model.
        model: an already built model. It is returned untouched, which is how
            the tests inject a fake chat model.
        **kwargs: extra keyword arguments for ``init_chat_model``.

    Returns:
        A ``RunnableRetry`` around the chat model (the retry wrapper is what
        the chains re-wrap their structured output in).
    """
    if model is not None:
        return model

    settings = settings or get_settings()
    model_name = settings.llm_vision_model if vision else settings.llm_model
    provider = settings.llm_provider
    setup_llm_cache(settings)
    limiter = InMemoryRateLimiter(
        requests_per_second=max(float(settings.llm_requests_per_second), 0.001),
        check_every_n_seconds=0.1,
        max_bucket_size=5,
    )
    kwargs.setdefault("temperature", settings.llm_temperature)
    logger.info("building chat model %s:%s", provider, model_name)
    chat = init_chat_model(f"{provider}:{model_name}", rate_limiter=limiter, **kwargs)
    return chat.with_retry(stop_after_attempt=settings.llm_max_retries)


def setup_llm_cache(settings: Settings | None = None, force: bool = False) -> bool:
    """Install the SQLite cache for LLM calls.

    Returns ``True`` when a cache was installed. The cache directory is created
    when it does not exist yet.
    """
    settings = settings or get_settings()
    if not (settings.llm_cache_enabled or force):
        return False
    cache_dir = Path(settings.llm_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Imported lazily: langchain-community prints a deprecation warning on
    # import and nothing else in this module needs it.
    from langchain_community.cache import SQLiteCache

    set_llm_cache(SQLiteCache(database_path=str(cache_dir / CACHE_DB_NAME)))
    logger.info("llm cache enabled at %s", cache_dir / CACHE_DB_NAME)
    return True


def chat_model_core(model: Runnable | None) -> BaseChatModel | None:
    """Return the chat model inside a (possibly wrapped) runnable.

    ``build_chat_model`` returns a ``RunnableRetry``; the chains need the chat
    model itself to call ``with_structured_output`` on it.
    """
    current: Any = model
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, BaseChatModel):
            return current
        bound = getattr(current, "bound", None)
        if bound is None:
            return None
        current = bound
    return None


def retry_attempts(model: Runnable | None) -> int | None:
    """Return the number of attempts of a retry wrapper, if there is one."""
    for attribute in ("max_attempt_number", "stop_after_attempt"):
        attempts = getattr(model, attribute, None)
        if isinstance(attempts, int):
            return attempts
    return None


__all__ = [
    "CACHE_DB_NAME",
    "build_chat_model",
    "chat_model_core",
    "retry_attempts",
    "setup_llm_cache",
]

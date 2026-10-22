"""The settings must be read from the environment and from the ``.env`` file."""

from __future__ import annotations

from pathlib import Path

from shared.config import Settings, get_settings


def test_the_defaults_are_safe() -> None:
    settings = Settings(_env_file=None)
    assert settings.respect_robots_txt is True
    assert settings.download_delay_seconds >= 1.0
    assert settings.digikey_rate_limit_per_day <= 1000
    assert settings.mouser_rate_limit_per_minute <= 30
    assert "contact" in settings.user_agent
    assert settings.llm_provider == "openai"


def test_the_comma_separated_origins_are_split(tmp_path: Path) -> None:
    """A ``.env`` file holds a plain string, not a JSON list."""
    env = tmp_path / ".env"
    env.write_text(
        "PARTPILOT_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:4173\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=env)
    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:4173"]


def test_the_llm_endpoint_is_configurable(tmp_path: Path) -> None:
    """The base URL, the model and the key come from the environment."""
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "PARTPILOT_LLM_PROVIDER=openai",
                "PARTPILOT_LLM_BASE_URL=http://127.0.0.1:1337/v1",
                "PARTPILOT_LLM_MODEL=moonshotai/kimi-k2.6:free",
                "PARTPILOT_LLM_API_KEY=a-test-key",
                "",
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(_env_file=env)
    assert settings.llm_provider == "openai"
    assert settings.llm_base_url == "http://127.0.0.1:1337/v1"
    assert settings.llm_model == "moonshotai/kimi-k2.6:free"
    assert settings.llm_api_key.get_secret_value() == "a-test-key"


def test_the_llm_endpoint_is_empty_by_default() -> None:
    """Empty means: the provider uses its own URL and its own key."""
    settings = Settings(_env_file=None)
    assert settings.llm_base_url == ""
    assert settings.llm_api_key.get_secret_value() == ""


def test_the_settings_are_cached() -> None:
    get_settings.cache_clear()
    assert get_settings() is get_settings()


def test_a_secret_never_shows_up_in_the_repr() -> None:
    """A key must not end up in a log line or in a traceback (NFR-02)."""
    settings = Settings(
        _env_file=None,
        llm_api_key="super-secret",
        digikey_client_secret="also-secret",
        nexar_client_secret="yet-another",
        mouser_api_key="a-fourth",
    )
    rendered = repr(settings)
    for secret in ("super-secret", "also-secret", "yet-another", "a-fourth"):
        assert secret not in rendered
    # The field is still there, only the value is hidden.
    assert "llm_api_key" in rendered

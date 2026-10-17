import importlib
import logging

from config.ai_mode import resolve_ai_mode


def test_defaults_to_mock():
    assert resolve_ai_mode("", "", "") == "mock"


def test_live_without_key_falls_back_to_mock(caplog):
    with caplog.at_level(logging.WARNING):
        assert resolve_ai_mode("live", "", "some-model") == "mock"
    assert "GEMINI_API_KEY is empty" in caplog.text


def test_live_without_model_falls_back_to_mock():
    assert resolve_ai_mode("live", "fake-key", "") == "mock"


def test_unknown_mode_falls_back_to_mock():
    assert resolve_ai_mode("turbo", "fake-key", "some-model") == "mock"


def test_live_with_key_and_model_is_live():
    # Only checks the decision; no API is called anywhere in this test suite.
    assert resolve_ai_mode(" LIVE ", "fake-key", "some-model") == "live"


def test_settings_module_does_not_crash_when_live_has_no_key(monkeypatch):
    # Re-run the real config/settings.py with AI_MODE=live and an empty key.
    monkeypatch.setenv("AI_MODE", "live")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_MODEL", "some-model")
    import config.settings

    reloaded = importlib.reload(config.settings)

    assert reloaded.AI_MODE == "mock"


def test_test_settings_never_go_live(settings):
    # config/settings_test.py forces mock so a developer's real .env can't leak into tests.
    assert settings.AI_MODE == "mock"
    assert settings.GEMINI_API_KEY == ""

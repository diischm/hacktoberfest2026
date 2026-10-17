"""
analyze_image in mock and live mode. Live mode always uses a fake client (monkeypatch replaces
ai.gemini._make_client), so these tests never touch the network or the real API.
"""

import json
import logging

import httpx
import pytest
from google.genai import errors as genai_errors
from google.genai import types

from ai import gemini
from ai.errors import AiRateLimited, AiUnavailable
from ai.mock import MOCK_ANSWERS
from ai.schema import AnalysisResult
from ai.service import analyze_image
from reports.choices import HazardType
from tests.ai_helpers import FakeClient, FakeClock, gemini_response, make_photo

FAKE_KEY = "AIzaFAKE-test-key-1234567890"
GOOD_ANSWER = {
    "hazard_type": "car_in_bike_lane",
    "description": "A car is parked in the bike lane.",
    "confidence": 0.9,
    "visible_evidence": ["bike lane", "parked car"],
    "needs_review": False,
}


def rate_limit_error(delay="37s"):
    return genai_errors.ClientError(
        429,
        {
            "error": {
                "code": 429,
                "message": "You exceeded your current quota.",
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}
                ],
            }
        },
    )


def server_error():
    return genai_errors.ServerError(
        503, {"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}}
    )


# --- mock mode (the test settings default) -----------------------------------------------


def test_mock_returns_valid_deterministic_result():
    photo = make_photo()
    first = analyze_image(photo, "image/jpeg")
    assert isinstance(first, AnalysisResult)
    assert first.hazard_type in HazardType.values
    assert first.description.startswith("[MOCK]")
    assert first.raw_response["mock"] is True
    assert analyze_image(photo, "image/jpeg") == first


def test_every_mock_answer_is_valid():
    for data in MOCK_ANSWERS:
        assert AnalysisResult.model_validate(data).description.startswith("[MOCK]")


def test_mock_forced_rate_limited(settings):
    settings.AI_MOCK_FORCE = "rate_limited"
    with pytest.raises(AiRateLimited) as info:
        analyze_image(make_photo(), "image/jpeg")
    assert info.value.retry_after_seconds == 60


def test_mock_forced_unavailable(settings):
    settings.AI_MOCK_FORCE = "unavailable"
    with pytest.raises(AiUnavailable):
        analyze_image(make_photo(), "image/jpeg")


def test_non_image_is_unavailable_in_mock_mode():
    with pytest.raises(AiUnavailable, match="not_an_image"):
        analyze_image(b"definitely not a photo", "image/jpeg")
    with pytest.raises(AiUnavailable, match="not_an_image"):
        analyze_image(make_photo(), "application/pdf")


def test_no_live_client_under_test_settings(monkeypatch):
    # Test settings have no key, so even AI_MODE=live must stay on mock.
    def explode(api_key):
        raise AssertionError("a live Gemini client was created in a test")

    monkeypatch.setattr(gemini, "_make_client", explode)
    assert analyze_image(make_photo(), "image/jpeg").description.startswith("[MOCK]")


def test_live_mode_without_key_uses_mock(settings, monkeypatch):
    settings.AI_MODE = "live"
    settings.GEMINI_MODEL = "fake-model"
    monkeypatch.setattr(gemini, "_make_client", lambda api_key: pytest.fail("client created"))
    assert analyze_image(make_photo(), "image/jpeg").description.startswith("[MOCK]")


# --- live mode with a fake client --------------------------------------------------------


@pytest.fixture
def live(settings, monkeypatch):
    """Switch to live mode with a fake key; returns a function that installs a FakeClient."""
    settings.AI_MODE = "live"
    settings.GEMINI_API_KEY = FAKE_KEY
    settings.GEMINI_MODEL = "fake-model"
    monkeypatch.setattr(gemini, "RETRY_DELAY_SECONDS", 0)

    def install(*outcomes):
        client = FakeClient(*outcomes)
        monkeypatch.setattr(gemini, "_make_client", lambda api_key: client)
        return client

    return install


def test_live_good_answer(live):
    client = live(gemini_response(json.dumps(GOOD_ANSWER)))

    result = analyze_image(make_photo(size=(3000, 2000), gps=True), "image/jpeg")

    assert result.hazard_type == "car_in_bike_lane"
    assert result.needs_review is False
    assert result.raw_response["model"] == "fake-model"
    assert result.raw_response["prompt_version"]
    json.dumps(result.raw_response)  # storable in a JSONField
    call = client.models.calls[0]
    assert call["model"] == "fake-model"
    assert call["config"].response_mime_type == "application/json"
    assert call["contents"][0].inline_data.mime_type == "image/jpeg"


@pytest.mark.parametrize(
    "text",
    [
        "this is not json",
        json.dumps({"hazard_type": "pothole_damage"}),
        json.dumps({**GOOD_ANSWER, "description": ""}),
    ],
    ids=["invalid-json", "missing-fields", "empty-description"],
)
def test_live_bad_answer_is_unavailable_with_raw(live, text):
    live(gemini_response(text))
    with pytest.raises(AiUnavailable) as info:
        analyze_image(make_photo(), "image/jpeg")
    assert info.value.raw_response["response"]  # kept for debugging


def test_live_wrong_enum_becomes_other(live):
    live(gemini_response(json.dumps({**GOOD_ANSWER, "hazard_type": "unicorn"})))
    result = analyze_image(make_photo(), "image/jpeg")
    assert (result.hazard_type, result.needs_review) == ("other", True)


def test_live_429_is_rate_limited_without_retry(live):
    client = live(rate_limit_error("37.2s"), gemini_response(json.dumps(GOOD_ANSWER)))
    with pytest.raises(AiRateLimited) as info:
        analyze_image(make_photo(), "image/jpeg")
    assert info.value.retry_after_seconds == 38
    assert len(client.models.calls) == 1  # no retry on 429


def test_live_429_without_delay(live):
    live(genai_errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}))
    with pytest.raises(AiRateLimited) as info:
        analyze_image(make_photo(), "image/jpeg")
    assert info.value.retry_after_seconds is None


def test_live_5xx_is_retried_once_then_succeeds(live):
    client = live(server_error(), gemini_response(json.dumps(GOOD_ANSWER)))
    assert analyze_image(make_photo(), "image/jpeg").hazard_type == "car_in_bike_lane"
    assert len(client.models.calls) == 2


def test_live_5xx_twice_is_unavailable(live):
    client = live(server_error(), server_error(), gemini_response(json.dumps(GOOD_ANSWER)))
    with pytest.raises(AiUnavailable, match="server_error 503"):
        analyze_image(make_photo(), "image/jpeg")
    assert len(client.models.calls) == 2  # one retry max


def test_live_timeout_is_unavailable_without_retry(live):
    client = live(httpx.ReadTimeout("timed out"))
    with pytest.raises(AiUnavailable, match="timeout"):
        analyze_image(make_photo(), "image/jpeg")
    assert len(client.models.calls) == 1


def test_live_other_api_error_is_unavailable(live):
    live(genai_errors.ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT"}}))
    with pytest.raises(AiUnavailable, match="api_error 400 INVALID_ARGUMENT"):
        analyze_image(make_photo(), "image/jpeg")


def test_live_unexpected_error_is_unavailable(live):
    live(RuntimeError("boom"))
    with pytest.raises(AiUnavailable, match="unexpected_error"):
        analyze_image(make_photo(), "image/jpeg")


# --- the API key never leaks -------------------------------------------------------------


@pytest.mark.parametrize(
    "outcome",
    [
        genai_errors.ClientError(
            400, {"error": {"code": 400, "message": f"API key {FAKE_KEY} not valid"}}
        ),
        rate_limit_error(),
        server_error(),
        httpx.ConnectError(f"failed for key={FAKE_KEY}"),
        RuntimeError(f"weird {FAKE_KEY}"),
    ],
    ids=["invalid-key", "429", "5xx", "connect", "unexpected"],
)
def test_api_key_never_in_errors_or_logs(live, caplog, outcome):
    live(outcome, outcome)
    with caplog.at_level(logging.DEBUG), pytest.raises((AiUnavailable, AiRateLimited)) as info:
        analyze_image(make_photo(), "image/jpeg")
    exc = info.value
    assert FAKE_KEY not in str(exc)
    assert FAKE_KEY not in repr(exc)
    assert FAKE_KEY not in json.dumps(getattr(exc, "raw_response", None))
    assert exc.__cause__ is None  # the SDK error (with the raw body) isn't attached
    assert FAKE_KEY not in caplog.text


# --- time budget (fake clock, no real waiting) -------------------------------------------


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(gemini, "_clock", fake.monotonic)
    monkeypatch.setattr(gemini, "_sleep", fake.sleep)
    return fake


def install_slow_client(monkeypatch, clock, seconds_per_call, *outcomes):
    def advance():
        clock.now += seconds_per_call

    client = FakeClient(*outcomes, on_call=advance)
    monkeypatch.setattr(gemini, "_make_client", lambda api_key: client)
    return client


def test_worst_case_fits_the_deadline_and_the_frontend_timeout():
    # One retry only starts if delay + a full attempt fit, so the worst case is the deadline.
    assert gemini.RETRY_DELAY_SECONDS + gemini.TIMEOUT_SECONDS <= gemini.DEADLINE_SECONDS
    assert gemini.DEADLINE_SECONDS < 30  # the frontend gives up after 30 s


def test_quick_5xx_is_retried_within_the_deadline(live, monkeypatch, clock):
    monkeypatch.setattr(gemini, "RETRY_DELAY_SECONDS", 1.0)
    start = clock.now
    # 3 s fail + 1 s delay leaves 16 s >= 15 s for a full attempt.
    client = install_slow_client(
        monkeypatch, clock, 3, server_error(), gemini_response(json.dumps(GOOD_ANSWER))
    )
    assert analyze_image(make_photo(), "image/jpeg").hazard_type == "car_in_bike_lane"
    assert len(client.models.calls) == 2
    assert clock.now - start == 3 + 1 + 3  # the delay went through the fake sleep


def test_slow_5xx_is_not_retried_when_no_full_attempt_fits(live, monkeypatch, clock):
    monkeypatch.setattr(gemini, "RETRY_DELAY_SECONDS", 1.0)
    start = clock.now
    # 6 s fail leaves 14 s: less than delay + 15 s, so give up now instead of overrunning.
    client = install_slow_client(
        monkeypatch, clock, 6, server_error(), gemini_response(json.dumps(GOOD_ANSWER))
    )
    with pytest.raises(AiUnavailable, match="server_error 503"):
        analyze_image(make_photo(), "image/jpeg")
    assert len(client.models.calls) == 1
    assert clock.now - start == 6  # no sleep either


# --- thinking level ----------------------------------------------------------------------


def test_thinking_level_off_by_default(live):
    client = live(gemini_response(json.dumps(GOOD_ANSWER)))
    analyze_image(make_photo(), "image/jpeg")
    assert client.models.calls[0]["config"].thinking_config is None


def test_thinking_level_from_settings(live, settings):
    settings.GEMINI_THINKING_LEVEL = "low"
    client = live(gemini_response(json.dumps(GOOD_ANSWER)))
    analyze_image(make_photo(), "image/jpeg")
    thinking = client.models.calls[0]["config"].thinking_config
    assert thinking.thinking_level == types.ThinkingLevel.LOW


def test_unknown_thinking_level_is_ignored(live, settings, caplog):
    settings.GEMINI_THINKING_LEVEL = "turbo"
    client = live(gemini_response(json.dumps(GOOD_ANSWER)))
    analyze_image(make_photo(), "image/jpeg")
    assert client.models.calls[0]["config"].thinking_config is None
    assert "GEMINI_THINKING_LEVEL" in caplog.text


def test_prepared_bytes_are_not_prepared_again(monkeypatch):
    from ai import service

    monkeypatch.setattr(service, "prepare_image", lambda b: pytest.fail("prepared twice"))
    assert analyze_image(make_photo(), "image/jpeg", prepared=True).description

"""
POST /api/reports/ (E5). The AI always runs in mock mode here (config/settings_test.py);
AI_MOCK_FORCE picks the error paths. Photos go to a temporary MEDIA_ROOT (tests/conftest.py).
"""

import io
import re
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils.crypto import get_random_string
from PIL import Image

from reports import limits
from reports.models import Report
from tests.ai_helpers import GPS_IFD, make_photo
from tests.test_api_errors import assert_error_shape
from tests.test_reports_api import REPORT_TYPES, assert_report_shape

pytestmark = pytest.mark.django_db

URL = "/api/reports/"
INSIDE = {"lat": "41.9962", "lng": "21.4316"}  # Macedonia Square, inside meta.map.bounds


def photo_file(content=None, name="hazard.jpg", content_type="image/jpeg"):
    return SimpleUploadedFile(name, content or make_photo(), content_type=content_type)


def upload(client, **overrides):
    data = {"photo": photo_file(), **INSIDE, **overrides}
    return client.post(URL, {k: v for k, v in data.items() if v is not None})


def stored_files(settings):
    root = Path(settings.MEDIA_ROOT)
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


# --- happy path ---------------------------------------------------------------------------


def test_upload_returns_201_with_the_report_shape(client):
    response = upload(client, note="Every morning around 8")

    assert response.status_code == 201
    body = response.json()
    assert_report_shape(body, REPORT_TYPES)
    assert "ai_raw_response" not in body
    assert body["lat"] == 41.9962 and body["lng"] == 21.4316
    assert body["note"] == "Every morning around 8"
    assert body["description"].startswith("[MOCK]")
    assert body["is_synthetic"] is False
    assert body["feedback_counts"] == {"still_there": 0, "resolved": 0, "dispute": 0}
    assert body["last_confirmed_at"] == body["created_at"]
    # Status follows needs_review (mock answers include a low-confidence one).
    expected = "ai_flagged" if body["needs_review"] else "unverified"
    assert body["verification_status"] == expected


def test_photo_url_is_root_relative_dated_and_random(client):
    url = upload(client).json()["photo_url"]
    assert re.fullmatch(r"/media/reports/\d{4}/\d{2}/[0-9a-f]{32}\.jpg", url)


def test_raw_ai_answer_is_stored_not_returned(client):
    body = upload(client).json()
    assert Report.objects.get(pk=body["id"]).ai_raw_response["mock"] is True


def test_stored_photo_is_the_cleaned_jpeg_not_the_original(client, settings):
    original = make_photo(size=(3000, 2000), gps=True)
    with Image.open(io.BytesIO(original)) as img:
        assert img.getexif().get_ifd(GPS_IFD)  # the test photo really has GPS data

    body = upload(client, photo=photo_file(original)).json()

    report = Report.objects.get(pk=body["id"])
    saved = Path(report.photo.path).read_bytes()
    assert saved != original
    assert [p.read_bytes() for p in stored_files(settings)] == [saved]  # only one file
    with Image.open(io.BytesIO(saved)) as img:
        assert img.format == "JPEG"
        assert max(img.size) == 1600
        assert len(img.getexif()) == 0
        assert "exif" not in img.info


@pytest.mark.parametrize(
    "fmt, mode, mime",
    [("PNG", "RGBA", "image/png"), ("WEBP", "RGB", "image/webp")],
)
def test_png_and_webp_are_accepted_and_stored_as_jpeg(client, fmt, mode, mime):
    content = make_photo(fmt=fmt, mode=mode, color=(0, 128, 0, 128) if mode == "RGBA" else "green")
    response = upload(client, photo=photo_file(content, name="p." + fmt.lower(), content_type=mime))
    assert response.status_code == 201
    assert response.json()["photo_url"].endswith(".jpg")


def test_new_report_appears_in_the_list(client):
    report_id = upload(client).json()["id"]
    features = client.get(URL).json()["features"]
    assert report_id in [f["id"] for f in features]


def test_upload_starts_a_session(client):
    response = upload(client)
    assert response.status_code == 201
    assert response.cookies["sessionid"].value


# --- AI outcomes --------------------------------------------------------------------------


def test_ai_rate_limited_is_429_and_saves_nothing(client, settings):
    settings.AI_MOCK_FORCE = "rate_limited"

    response = upload(client)

    error = assert_error_shape(response, 429, "ai_rate_limited")
    assert error["retry_after_seconds"] == 60
    assert response["Retry-After"] == "60"
    assert Report.objects.count() == 0
    assert stored_files(settings) == []


def test_ai_unavailable_still_creates_a_flagged_report(client, settings):
    settings.AI_MOCK_FORCE = "unavailable"

    response = upload(client)

    assert response.status_code == 201
    body = response.json()
    assert_report_shape(body, REPORT_TYPES)
    assert body["hazard_type"] == "other"
    assert body["description"] == ""
    assert body["ai_confidence"] is None
    assert body["needs_review"] is True
    assert body["verification_status"] == "ai_flagged"
    assert body["condition"] == "grey"
    assert body["photo_url"]
    raw = Report.objects.get(pk=body["id"]).ai_raw_response
    assert raw == {"error": "mock_forced_unavailable", "response": {"mock": True}}


def test_failed_database_write_leaves_no_photo_file(client, settings, monkeypatch):
    def broken_save(self, *args, **kwargs):
        raise RuntimeError("database is gone")

    monkeypatch.setattr(Report, "save", broken_save)

    assert_error_shape(upload(client), 500, "server_error")
    assert stored_files(settings) == []


# --- validation ---------------------------------------------------------------------------


def test_missing_fields_are_validation_errors(client):
    error = assert_error_shape(client.post(URL, {}), 400, "validation_error")
    assert set(error["fields"]) == {"photo", "lat", "lng"}


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"lat": "41.0"}, "lat"),  # valid latitude, but outside the map area
        ({"lng": "22.0"}, "lng"),
        ({"lat": "91"}, "lat"),
        ({"lng": "-181"}, "lng"),
        ({"lat": "abc"}, "lat"),
        ({"lat": "nan"}, "lat"),
        ({"note": "x" * (limits.MAX_NOTE_LENGTH + 1)}, "note"),
        ({"photo": "not a file"}, "photo"),
    ],
)
def test_bad_fields_are_validation_errors(client, settings, overrides, field):
    error = assert_error_shape(upload(client, **overrides), 400, "validation_error")
    assert field in error["fields"]
    assert Report.objects.count() == 0
    assert stored_files(settings) == []


def test_note_at_the_limit_is_fine(client):
    assert upload(client, note="x" * limits.MAX_NOTE_LENGTH).status_code == 201


def test_json_body_is_a_validation_error(client):
    response = client.post(URL, {**INSIDE}, content_type="application/json")
    assert "photo" in assert_error_shape(response, 400, "validation_error")["fields"]


@pytest.mark.parametrize(
    "content, name, content_type",
    [
        (b"%PDF-1.4 definitely not a photo", "hazard.jpg", "image/jpeg"),  # renamed, lying type
        (make_photo(fmt="GIF", mode="P"), "hazard.gif", "image/gif"),  # an image, not accepted
        (make_photo(fmt="GIF", mode="P"), "hazard.jpg", "image/jpeg"),
        (make_photo()[:200], "hazard.jpg", "image/jpeg"),  # truncated JPEG
    ],
    ids=["pdf-renamed", "gif", "gif-renamed", "truncated"],
)
def test_unsupported_photo_is_415(client, settings, content, name, content_type):
    response = upload(client, photo=photo_file(content, name=name, content_type=content_type))
    assert_error_shape(response, 415, "unsupported_photo_type")
    assert Report.objects.count() == 0
    assert stored_files(settings) == []


def test_oversize_photo_is_413(client, settings, monkeypatch):
    content = make_photo()
    monkeypatch.setattr(limits, "MAX_PHOTO_BYTES", len(content) - 1)

    assert_error_shape(upload(client, photo=photo_file(content)), 413, "photo_too_large")
    assert Report.objects.count() == 0
    assert stored_files(settings) == []


def test_photo_exactly_at_the_limit_is_fine(client, monkeypatch):
    content = make_photo()
    monkeypatch.setattr(limits, "MAX_PHOTO_BYTES", len(content))
    assert upload(client, photo=photo_file(content)).status_code == 201


# --- CSRF ---------------------------------------------------------------------------------


@pytest.fixture
def csrf_client():
    # The normal test client skips CSRF checks; this one enforces them like a real browser.
    return Client(enforce_csrf_checks=True)


def test_post_without_csrf_token_is_403(csrf_client):
    assert_error_shape(upload(csrf_client), 403, "csrf_failed")
    assert Report.objects.count() == 0


def test_post_with_cookie_but_no_header_is_403(csrf_client):
    csrf_client.cookies["csrftoken"] = get_random_string(32)
    assert_error_shape(upload(csrf_client), 403, "csrf_failed")


def test_post_with_wrong_token_is_403(csrf_client):
    csrf_client.cookies["csrftoken"] = get_random_string(32)
    data = {"photo": photo_file(), **INSIDE}
    response = csrf_client.post(URL, data, headers={"X-CSRFToken": get_random_string(32)})
    assert_error_shape(response, 403, "csrf_failed")


def test_post_with_csrf_token_is_201(csrf_client):
    token = get_random_string(32)
    csrf_client.cookies["csrftoken"] = token
    data = {"photo": photo_file(), **INSIDE}
    response = csrf_client.post(URL, data, headers={"X-CSRFToken": token})
    assert response.status_code == 201


def test_get_needs_no_csrf_token(csrf_client):
    assert csrf_client.get(URL).status_code == 200


# --- throttle -----------------------------------------------------------------------------


def test_seventh_upload_in_a_minute_is_429(client):
    for _ in range(6):
        assert upload(client).status_code == 201

    response = upload(client)

    error = assert_error_shape(response, 429, "ai_rate_limited")
    assert isinstance(error["retry_after_seconds"], int) and error["retry_after_seconds"] > 0
    assert response["Retry-After"] == str(error["retry_after_seconds"])
    assert Report.objects.count() == 6


def test_throttle_rate_comes_from_settings(client, settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {"report_upload": "1/min"},
    }
    assert upload(client).status_code == 201
    assert_error_shape(upload(client), 429, "ai_rate_limited")


def test_reading_is_not_throttled(client, settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {"report_upload": "1/min"},
    }
    upload(client)
    for _ in range(5):
        assert client.get(URL).status_code == 200

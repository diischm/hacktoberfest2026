"""
Contract conformance for E2, E3, E4 (docs/plan/API_CONTRACT.md).

The expected keys and the E2 body are copied by hand from the contract so that drift between
code and contract fails a test. Change them only together with a contract change.
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from PIL import Image

from reports.choices import FeedbackAction, HazardType, VerificationStatus
from reports.models import Report, ReportFeedback

pytestmark = pytest.mark.django_db

CONTRACT_META = {
    "contract_version": 2,
    "hazard_types": [
        {"key": "road_block", "label": "Road blocked", "icon": "barrier", "is_hazard": True},
        {"key": "car_on_sidewalk", "label": "Car on sidewalk", "icon": "car", "is_hazard": True},
        {"key": "car_on_crosswalk", "label": "Car on crosswalk", "icon": "car", "is_hazard": True},
        {"key": "car_in_bike_lane", "label": "Car in bike lane", "icon": "car", "is_hazard": True},
        {
            "key": "pothole_damage",
            "label": "Pothole / damage",
            "icon": "pothole",
            "is_hazard": True,
        },
        {
            "key": "construction_debris",
            "label": "Construction debris",
            "icon": "cone",
            "is_hazard": True,
        },
        {
            "key": "informal_shortcut",
            "label": "Informal shortcut path",
            "icon": "footpath",
            "is_hazard": False,
        },
        {"key": "other", "label": "Other", "icon": "warning", "is_hazard": True},
        {"key": "none", "label": "No hazard found", "icon": "check", "is_hazard": False},
    ],
    "conditions": [
        {"key": "green", "hex": "#2E7D32", "label": "Clear", "meaning": "Clear / comfortable"},
        {
            "key": "amber",
            "hex": "#F9A825",
            "label": "Caution",
            "meaning": "Minor issue or aging report",
        },
        {"key": "red", "hex": "#C62828", "label": "Hazard", "meaning": "Fresh, significant hazard"},
        {
            "key": "grey",
            "hex": "#757575",
            "label": "Unknown",
            "meaning": "Unknown, stale, disputed or needs review",
        },
    ],
    "verification_statuses": [
        {"key": "unverified", "label": "Unverified"},
        {"key": "ai_flagged", "label": "Needs review"},
        {"key": "community_confirmed", "label": "Confirmed by riders"},
        {"key": "verified", "label": "Verified"},
        {"key": "disputed", "label": "Disputed"},
        {"key": "resolved", "label": "Resolved"},
    ],
    "feedback_actions": [
        {"key": "still_there", "label": "Still there"},
        {"key": "resolved", "label": "It's gone"},
        {"key": "dispute", "label": "Not accurate"},
    ],
    "segment_kinds": [
        {
            "key": "bike_lane",
            "label": "Bike lane or cycleway",
            "hex": "#1565C0",
            "line_style": "solid",
        },
        {"key": "shared_path", "label": "Shared path", "hex": "#00838F", "line_style": "dashed"},
        {"key": "road", "label": "On-street (no lane)", "hex": "#6D4C41", "line_style": "dotted"},
        {
            "key": "informal_path",
            "label": "Informal path",
            "hex": "#8D6E63",
            "line_style": "dashed",
        },
    ],
    "bike_parking": {"label": "Bicycle parking", "hex": "#0D47A1"},
    "upload": {
        "max_photo_bytes": 10485760,
        "accepted_types": ["image/jpeg", "image/png", "image/webp"],
        "max_note_length": 500,
    },
    "map": {
        "center": {"lat": 41.9962, "lng": 21.4316},
        "zoom": 15,
        "bounds": {"min_lat": 41.95, "min_lng": 21.30, "max_lat": 42.05, "max_lng": 21.55},
    },
}

NUMBER = (int, float)
REPORT_TYPES = {
    "id": int,
    "lat": NUMBER,
    "lng": NUMBER,
    "hazard_type": str,
    "description": str,
    "note": str,
    "ai_confidence": (*NUMBER, type(None)),
    "needs_review": bool,
    "verification_status": str,
    "condition": str,
    "freshness_weight": NUMBER,
    "created_at": str,
    "last_confirmed_at": str,
    "photo_url": (str, type(None)),
    "is_synthetic": bool,
    "feedback_counts": dict,
}
PROPERTY_TYPES = {k: v for k, v in REPORT_TYPES.items() if k not in ("lat", "lng")}
CONDITIONS = {"green", "amber", "red", "grey"}

# A known fixture report: car_in_bike_lane at Macedonia Square.
KNOWN_ID, KNOWN_LAT, KNOWN_LNG = 9001, 41.99621, 21.43162


@pytest.fixture
def demo():
    call_command("loaddata", "demo_reports", verbosity=0)


def assert_report_shape(obj, expected_types):
    assert set(obj) == set(expected_types)
    for key, expected in expected_types.items():
        assert isinstance(obj[key], expected), key
        if expected is NUMBER or expected == int:
            assert not isinstance(obj[key], bool), key  # bool is an int in Python
    assert obj["hazard_type"] in HazardType.values
    assert obj["verification_status"] in VerificationStatus.values
    assert obj["condition"] in CONDITIONS
    assert 0 <= obj["freshness_weight"] <= 1
    assert set(obj["feedback_counts"]) == {"still_there", "resolved", "dispute"}
    assert all(type(n) is int for n in obj["feedback_counts"].values())
    for key in ("created_at", "last_confirmed_at"):
        assert obj[key][-6:] in ("+01:00", "+02:00"), key  # Europe/Skopje offset, not "Z"


def bbox(*values):
    return {"bbox": ",".join(str(v) for v in values)}


# --- E2 meta ------------------------------------------------------------------------------


def test_meta_matches_contract_example_exactly(client):
    response = client.get("/api/meta/")
    assert response.status_code == 200
    assert response.json() == CONTRACT_META


def test_meta_lists_equal_textchoices(client):
    meta = client.get("/api/meta/").json()
    assert [h["key"] for h in meta["hazard_types"]] == HazardType.values
    assert [s["key"] for s in meta["verification_statuses"]] == VerificationStatus.values
    assert [a["key"] for a in meta["feedback_actions"]] == FeedbackAction.values


# --- E3 list ------------------------------------------------------------------------------


def test_list_is_geojson_with_contract_properties(client, demo):
    response = client.get("/api/reports/")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"type", "truncated", "features"}
    assert body["type"] == "FeatureCollection"
    assert body["truncated"] is False
    assert body["features"]
    for feature in body["features"]:
        assert set(feature) == {"type", "id", "geometry", "properties"}
        assert feature["type"] == "Feature"
        assert feature["id"] == feature["properties"]["id"]
        assert feature["geometry"]["type"] == "Point"
        assert len(feature["geometry"]["coordinates"]) == 2
        assert_report_shape(feature["properties"], PROPERTY_TYPES)


def test_list_coordinates_are_lng_lat(client, demo):
    features = client.get("/api/reports/").json()["features"]
    known = next(f for f in features if f["id"] == KNOWN_ID)
    assert known["geometry"]["coordinates"] == [KNOWN_LNG, KNOWN_LAT]


def test_list_is_newest_first_and_hides_resolved_by_default(client, demo):
    features = client.get("/api/reports/").json()["features"]
    expected = Report.objects.exclude(verification_status="resolved").order_by("-created_at")
    assert [f["id"] for f in features] == list(expected.values_list("id", flat=True))
    assert all(f["properties"]["verification_status"] != "resolved" for f in features)


def test_include_resolved(client, demo):
    resolved_ids = set(
        Report.objects.filter(verification_status="resolved").values_list("id", flat=True)
    )
    assert resolved_ids

    hidden = client.get("/api/reports/", {"include_resolved": "false"}).json()["features"]
    shown = client.get("/api/reports/", {"include_resolved": "true"}).json()["features"]

    assert resolved_ids.isdisjoint(f["id"] for f in hidden)
    assert resolved_ids <= {f["id"] for f in shown}
    assert len(shown) == Report.objects.count()


def test_include_resolved_bad_value_is_validation_error(client):
    response = client.get("/api/reports/", {"include_resolved": "yes"})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "include_resolved" in error["fields"]


def test_bbox_includes_and_excludes(client):
    inside = Report.objects.create(lat=41.996, lng=21.431)
    outside = Report.objects.create(lat=41.996, lng=21.500)

    ids = {
        f["id"]
        for f in client.get("/api/reports/", bbox(21.42, 41.99, 21.44, 42.0)).json()["features"]
    }
    assert ids == {inside.id}

    # Edges are inclusive.
    edge = client.get("/api/reports/", bbox(21.431, 41.996, 21.431, 41.996)).json()
    assert [f["id"] for f in edge["features"]] == [inside.id]

    # Without bbox: the whole map.bounds.
    all_ids = {f["id"] for f in client.get("/api/reports/").json()["features"]}
    assert all_ids == {inside.id, outside.id}


def test_default_bbox_is_map_bounds(client):
    Report.objects.create(lat=40.0, lng=20.0)  # outside the demo area
    assert client.get("/api/reports/").json()["features"] == []


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "1,2,3",
        "1,2,3,4,5",
        "a,b,c,d",
        "21.4,41.9,,42.0",
        "nan,41.9,21.5,42.0",
        "21.4,41.9,inf,42.0",
        "-181,41.9,21.5,42.0",
        "21.4,-91,21.5,42.0",
        "21.4,41.9,21.5,91",
        "21.5,41.9,21.4,42.0",  # min lng > max lng
        "21.4,42.0,21.5,41.9",  # min lat > max lat
    ],
)
def test_invalid_bbox_is_contract_error(client, raw):
    response = client.get("/api/reports/", {"bbox": raw})
    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "invalid_bbox"
    assert isinstance(body["error"]["message"], str)
    assert "bbox" in body["error"]["fields"]


def test_list_truncates_at_500(client):
    Report.objects.bulk_create(Report(lat=41.996, lng=21.431) for _ in range(501))
    body = client.get("/api/reports/").json()
    assert body["truncated"] is True
    assert len(body["features"]) == 500

    Report.objects.filter(pk=Report.objects.order_by("created_at", "id").first().pk).delete()
    body = client.get("/api/reports/").json()
    assert body["truncated"] is False
    assert len(body["features"]) == 500


def test_list_query_count_does_not_grow_with_reports(client, django_assert_max_num_queries):
    reports = Report.objects.bulk_create(Report(lat=41.996, lng=21.431) for _ in range(30))
    for i, report in enumerate(reports):
        ReportFeedback.objects.create(report=report, session_key=f"s{i}", action="still_there")

    with django_assert_max_num_queries(1):
        features = client.get("/api/reports/").json()["features"]

    assert len(features) == 30
    assert all(f["properties"]["feedback_counts"]["still_there"] == 1 for f in features)


# --- E4 detail ----------------------------------------------------------------------------


def test_detail_has_contract_fields(client, demo):
    response = client.get(f"/api/reports/{KNOWN_ID}/")
    assert response.status_code == 200
    body = response.json()
    assert_report_shape(body, REPORT_TYPES)
    assert body["lat"] == KNOWN_LAT
    assert body["lng"] == KNOWN_LNG
    assert body["created_at"] == "2026-10-17T08:05:00+02:00"
    assert body["last_confirmed_at"] == "2026-10-17T09:40:00+02:00"
    assert body["is_synthetic"] is True
    assert body["photo_url"] is None


def test_detail_returns_resolved_reports(client, demo):
    resolved = Report.objects.filter(verification_status="resolved").first()
    assert client.get(f"/api/reports/{resolved.id}/").status_code == 200


def test_detail_serialization_rules(client):
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
    report = Report.objects.create(
        lat=41.123456789,
        lng=21.987654321,
        photo=SimpleUploadedFile("p.png", buffer.getvalue(), content_type="image/png"),
        ai_raw_response={"secret": "do-not-leak"},
    )
    ReportFeedback.objects.create(report=report, session_key="session-secret", action="dispute")

    response = client.get(f"/api/reports/{report.id}/")
    body = response.json()

    assert body["lat"] == 41.123457
    assert body["lng"] == 21.987654
    assert body["last_confirmed_at"] == body["created_at"]  # null in DB -> created_at
    assert body["photo_url"] == report.photo.url
    assert body["photo_url"].startswith("/media/reports/")
    assert body["feedback_counts"] == {"still_there": 0, "resolved": 0, "dispute": 1}
    text = response.content.decode()
    assert "ai_raw_response" not in text
    assert "do-not-leak" not in text
    assert "session-secret" not in text

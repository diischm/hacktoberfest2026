"""
Contract conformance for E7 (bike segments) and E10 (bike parking), plus the geo helpers and the
fetch command's normalizer for reports/bike.py.

The data comes from the committed extract `reports/data/skopje_bike.geojson`, so these tests are
offline: they never touch the Overpass API.
"""

import pytest
from django.utils import timezone

from reports import bike
from reports.choices import Condition, HazardType, SegmentKind, VerificationStatus
from reports.meta import build_meta
from reports.models import Report

pytestmark = pytest.mark.django_db

CONDITIONS = {"green", "amber", "red", "grey"}
SEGMENT_PROPERTY_KEYS = {
    "id",
    "name",
    "kind",
    "condition",
    "score",
    "length_m",
    "hazard_report_ids",
    "is_synthetic",
}
PARKING_PROPERTY_KEYS = {"id", "name", "capacity", "covered", "parking", "access"}

# Real features in the committed extract, used to check bbox filtering.
KNOWN_LANE_ID = 16545231  # a way in central Skopje
KNOWN_LANE_LNG, KNOWN_LANE_LAT = 21.432133, 41.994877
KNOWN_PARKING_ID = 3508366301
KNOWN_PARKING_LNG, KNOWN_PARKING_LAT = 21.392381, 42.003979


def bbox(*values):
    return {"bbox": ",".join(str(v) for v in values)}


# --- Geo helpers --------------------------------------------------------------------------


def test_haversine_matches_a_known_distance():
    distance = bike.haversine_m((21.0, 42.0), (21.0, 42.001))
    assert 110 < distance < 112  # 0.001° of latitude
    assert bike.haversine_m((21.0, 42.0), (21.0, 42.0)) == 0


def test_point_to_segment_clamps_to_the_ends():
    # A point level with the middle of a horizontal segment.
    assert bike.point_to_segment_m((0.0005, 0.001), (0.0, 0.0), (0.001, 0.0)) == pytest.approx(
        111.2, abs=1
    )
    # Beyond the end: the distance is to the endpoint, not the infinite line.
    assert bike.point_to_segment_m((0.002, 0.0), (0.0, 0.0), (0.001, 0.0)) == pytest.approx(
        111.2, abs=1
    )
    # Degenerate segment (two equal points) is just a point distance.
    assert bike.point_to_segment_m((0.0, 0.0), (0.0, 0.0), (0.0, 0.0)) == 0


def test_point_to_line_uses_the_nearest_segment():
    line = [[0.0, 0.0], [0.001, 0.0], [0.002, 0.0]]
    assert bike.point_to_line_m((0.0015, 0.0), line) == pytest.approx(0, abs=1)
    assert bike.point_to_line_m((0.0015, 0.001), line) == pytest.approx(111.2, abs=1)


def test_line_length_and_bbox():
    line = [[21.0, 42.0], [21.0, 42.001]]
    assert bike.line_length_m(line) == pytest.approx(111.2, abs=1)
    assert bike.coords_bbox([[1, 2], [3, 4], [0, 5]]) == (0, 2, 3, 5)


def test_bboxes_overlap():
    assert bike.bboxes_overlap((0, 0, 1, 1), (0.5, 0.5, 2, 2)) is True
    assert bike.bboxes_overlap((0, 0, 1, 1), (1, 1, 2, 2)) is True  # touching counts
    assert bike.bboxes_overlap((0, 0, 1, 1), (2, 2, 3, 3)) is False


@pytest.mark.parametrize(
    "tags, expected",
    [
        ({"highway": "cycleway"}, SegmentKind.BIKE_LANE),
        ({"highway": "residential", "cycleway:left": "lane"}, SegmentKind.BIKE_LANE),
        ({"highway": "residential", "cycleway": "track"}, SegmentKind.BIKE_LANE),
        ({"highway": "path", "bicycle": "designated"}, SegmentKind.SHARED_PATH),
        ({"highway": "pedestrian", "bicycle": "yes"}, SegmentKind.SHARED_PATH),
        ({"highway": "residential", "bicycle": "yes"}, SegmentKind.ROAD),
        ({"highway": "path", "informal": "yes"}, SegmentKind.INFORMAL_PATH),
    ],
)
def test_segment_kind_from_tags(tags, expected):
    assert bike.segment_kind_from_tags(tags) == expected


def test_score_lane_picks_the_worst_condition_and_penalises():
    line = [[21.0, 42.0], [21.001, 42.0]]
    near = {"id": 7, "lng": 21.0005, "lat": 42.0, "condition": Condition.RED}
    far = {"id": 8, "lng": 22.0, "lat": 42.0, "condition": Condition.RED}

    condition, score, ids = bike.score_lane(line, [near, far])
    assert condition == Condition.RED
    assert score == 100 - bike.SCORE_PENALTY[Condition.RED]
    assert ids == [7]

    assert bike.score_lane(line, []) == (Condition.GREEN, 100, [])


# --- Committed extract --------------------------------------------------------------------


def test_dataset_is_loaded_from_the_committed_file():
    info = bike.dataset_info()
    assert info["lanes"] > 0
    assert info["parking"] > 0
    assert info["osm_timestamp"]


# --- E7 segments --------------------------------------------------------------------------


def test_segments_shape(client):
    response = client.get("/api/segments/")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"type", "osm_timestamp", "features"}
    assert body["type"] == "FeatureCollection"
    assert body["features"]
    for feature in body["features"]:
        assert set(feature) == {"type", "id", "geometry", "properties"}
        assert feature["type"] == "Feature"
        assert feature["id"] == feature["properties"]["id"]
        assert feature["geometry"]["type"] == "LineString"
        assert len(feature["geometry"]["coordinates"]) >= 2
        props = feature["properties"]
        assert set(props) == SEGMENT_PROPERTY_KEYS
        assert props["kind"] in SegmentKind.values
        assert props["condition"] in CONDITIONS
        assert 0 <= props["score"] <= 100
        assert props["length_m"] >= 0
        assert props["is_synthetic"] is False
        assert all(isinstance(i, int) for i in props["hazard_report_ids"])


def test_segments_bbox_includes_and_excludes(client):
    inside = client.get("/api/segments/", bbox(21.431, 41.994, 21.433, 41.996)).json()
    assert KNOWN_LANE_ID in {f["id"] for f in inside["features"]}

    empty = client.get("/api/segments/", bbox(0, 0, 0.01, 0.01)).json()
    assert empty["features"] == []


@pytest.mark.parametrize("raw", ["", "1,2,3", "a,b,c,d", "21.5,41.9,21.4,42.0"])
def test_segments_invalid_bbox(client, raw):
    response = client.get("/api/segments/", {"bbox": raw})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_bbox"


def test_segments_are_scored_by_nearby_reports(client):
    report = Report.objects.create(
        lat=KNOWN_LANE_LAT,
        lng=KNOWN_LANE_LNG,
        hazard_type=HazardType.CAR_IN_BIKE_LANE,
        verification_status=VerificationStatus.COMMUNITY_CONFIRMED,
        created_at=timezone.now(),
    )
    body = client.get("/api/segments/", bbox(21.431, 41.994, 21.433, 41.996)).json()
    lane = next(f for f in body["features"] if f["id"] == KNOWN_LANE_ID)
    assert lane["properties"]["condition"] == Condition.RED
    assert lane["properties"]["score"] < 100
    assert report.id in lane["properties"]["hazard_report_ids"]


def test_resolved_reports_do_not_score_segments(client):
    Report.objects.create(
        lat=KNOWN_LANE_LAT,
        lng=KNOWN_LANE_LNG,
        hazard_type=HazardType.CAR_IN_BIKE_LANE,
        verification_status=VerificationStatus.RESOLVED,
        created_at=timezone.now(),
    )
    body = client.get("/api/segments/", bbox(21.431, 41.994, 21.433, 41.996)).json()
    lane = next(f for f in body["features"] if f["id"] == KNOWN_LANE_ID)
    assert lane["properties"]["condition"] == Condition.GREEN
    assert lane["properties"]["hazard_report_ids"] == []


# --- E10 bike parking ---------------------------------------------------------------------


def test_bike_parking_shape(client):
    response = client.get("/api/bike-parking/")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"type", "osm_timestamp", "features"}
    assert body["features"]
    for feature in body["features"]:
        assert set(feature) == {"type", "id", "geometry", "properties"}
        assert feature["geometry"]["type"] == "Point"
        assert len(feature["geometry"]["coordinates"]) == 2
        assert set(feature["properties"]) == PARKING_PROPERTY_KEYS


def test_bike_parking_bbox_includes_and_excludes(client):
    inside = client.get("/api/bike-parking/", bbox(21.39, 42.003, 21.395, 42.005)).json()
    assert KNOWN_PARKING_ID in {f["id"] for f in inside["features"]}

    empty = client.get("/api/bike-parking/", bbox(0, 0, 0.01, 0.01)).json()
    assert empty["features"] == []


def test_bike_parking_invalid_bbox(client):
    response = client.get("/api/bike-parking/", {"bbox": "nope"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_bbox"


# --- E2 additions -------------------------------------------------------------------------


def test_meta_publishes_segment_kinds_and_bike_parking():
    meta = build_meta()
    assert meta["contract_version"] == 2
    assert [k["key"] for k in meta["segment_kinds"]] == SegmentKind.values
    for kind in meta["segment_kinds"]:
        assert kind["hex"].startswith("#")
        assert kind["line_style"] in {"solid", "dashed", "dotted"}
    assert meta["bike_parking"]["label"]
    assert meta["bike_parking"]["hex"].startswith("#")


# --- fetch_bike_data normalizer (no network) ----------------------------------------------


def test_normalize_turns_overpass_json_into_geojson():
    from reports.management.commands.fetch_bike_data import normalize

    raw = {
        "osm3s": {"timestamp_osm_base": "2026-01-01T00:00:00Z"},
        "elements": [
            {
                "type": "way",
                "id": 10,
                "geometry": [
                    {"lat": 41.99, "lon": 21.43},
                    {"lat": 41.991, "lon": 21.431},
                ],
                "tags": {"highway": "cycleway", "name": "Test Lane"},
            },
            {
                "type": "node",
                "id": 20,
                "lat": 41.995,
                "lon": 21.44,
                "tags": {"amenity": "bicycle_parking", "capacity": "12", "covered": "yes"},
            },
            # A way that is too short to be a LineString is dropped.
            {"type": "way", "id": 30, "geometry": [{"lat": 41.9, "lon": 21.4}], "tags": {}},
        ],
    }

    data = normalize(raw)

    assert data["osm_timestamp"] == "2026-01-01T00:00:00Z"
    assert [f["id"] for f in data["features"]] == [10, 20]
    lane, parking = data["features"]
    assert lane["geometry"]["type"] == "LineString"
    assert lane["geometry"]["coordinates"] == [[21.43, 41.99], [21.431, 41.991]]
    assert lane["properties"]["kind"] == SegmentKind.BIKE_LANE.value
    assert lane["properties"]["name"] == "Test Lane"
    assert parking["geometry"]["type"] == "Point"
    assert parking["geometry"]["coordinates"] == [21.44, 41.995]
    assert parking["properties"]["capacity"] == 12
    assert parking["properties"]["covered"] is True

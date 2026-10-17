import pytest
from django.utils import timezone

from reports.choices import HazardType, VerificationStatus
from reports.models import Report
from routes.scoring import _scenarios, score_route

# A short straight line along a street (west -> east), ~170 m.
LINE = [[21.4300, 41.9970], [21.4320, 41.9970]]
SCENARIO_KEYS = {"id", "name", "from", "to"}
ROUTE_KEYS = {
    "id",
    "name",
    "geometry",
    "length_m",
    "score",
    "condition",
    "hazards_on_route",
    "explanation",
}


def hazard(pk, lat, lng, condition="red", hazard_type=HazardType.CAR_IN_BIKE_LANE):
    return {
        "id": pk,
        "lat": lat,
        "lng": lng,
        "hazard_type": hazard_type,
        "condition": condition,
        "freshness_weight": 1.0,
    }


def test_hazard_near_route_lowers_score_and_sets_condition():
    clear = score_route(LINE, [], shortest_m=170)
    near = score_route(LINE, [hazard(1, 41.99705, 21.4310)], shortest_m=170)  # ~6 m away

    assert near["score"] < clear["score"]
    assert near["condition"] == "red"
    assert [h["id"] for h in near["hazards"]] == [1]
    assert clear["condition"] == "green"


def test_hazard_far_from_route_is_ignored():
    far = score_route(LINE, [hazard(1, 41.9990, 21.4310)], shortest_m=170)  # ~220 m away

    assert far["hazards"] == []
    assert far["score"] == score_route(LINE, [], shortest_m=170)["score"]


def test_red_costs_more_than_amber():
    red = score_route(LINE, [hazard(1, 41.9970, 21.4310, "red")], shortest_m=170)
    amber = score_route(LINE, [hazard(1, 41.9970, 21.4310, "amber")], shortest_m=170)

    assert red["score"] < amber["score"]


def test_duplicate_reports_count_once():
    one = score_route(LINE, [hazard(1, 41.9970, 21.4310)], shortest_m=170)
    twice = score_route(
        LINE, [hazard(1, 41.9970, 21.4310), hazard(2, 41.99701, 21.43101)], shortest_m=170
    )

    assert twice["score"] == one["score"]
    assert len(twice["hazards"]) == 2


@pytest.mark.django_db
def test_scenarios_shape(client):
    response = client.get("/api/routes/scenarios/")

    assert response.status_code == 200
    scenarios = response.json()["scenarios"]
    assert len(scenarios) >= 2
    for scenario in scenarios:
        assert set(scenario) == SCENARIO_KEYS
        assert set(scenario["from"]) == {"name", "lat", "lng"}


@pytest.mark.django_db
def test_compare_shape_and_order(client):
    scenario_id = _scenarios()[0]["id"]
    response = client.get("/api/routes/compare/", {"scenario": scenario_id})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"scenario", "recommended_route_id", "routes"}
    assert set(body["scenario"]) == SCENARIO_KEYS
    assert 2 <= len(body["routes"]) <= 3
    for route in body["routes"]:
        assert set(route) == ROUTE_KEYS
        assert route["geometry"]["type"] == "LineString"
        lng, lat = route["geometry"]["coordinates"][0]  # GeoJSON is [lng, lat]
        assert 21.30 < lng < 21.55 and 41.95 < lat < 42.05
        assert 0 <= route["score"] <= 100
        assert 2 <= len(route["explanation"]) <= 4
    scores = [r["score"] for r in body["routes"]]
    assert scores == sorted(scores, reverse=True)
    assert body["recommended_route_id"] == body["routes"][0]["id"]


@pytest.mark.django_db
def test_compare_hazard_on_one_route_changes_recommendation(client):
    scenario = _scenarios()[0]
    body = client.get("/api/routes/compare/", {"scenario": scenario["id"]}).json()
    best = body["recommended_route_id"]
    route = next(r for r in scenario["routes"] if r["id"] == best)
    lng, lat = route["coordinates"][len(route["coordinates"]) // 2]
    now = timezone.now()
    for i in range(3):  # three different confirmed hazards on the current best route
        Report.objects.create(
            lat=lat + i * 0.0001,
            lng=lng,
            hazard_type=[HazardType.ROAD_BLOCK, HazardType.POTHOLE_DAMAGE, HazardType.OTHER][i],
            verification_status=VerificationStatus.VERIFIED,
            created_at=now,
        )

    after = client.get("/api/routes/compare/", {"scenario": scenario["id"]}).json()

    assert after["recommended_route_id"] != best


@pytest.mark.django_db
def test_resolved_report_is_ignored(client):
    scenario = _scenarios()[0]
    lng, lat = scenario["routes"][0]["coordinates"][5]
    Report.objects.create(
        lat=lat,
        lng=lng,
        hazard_type=HazardType.ROAD_BLOCK,
        verification_status=VerificationStatus.RESOLVED,
    )

    body = client.get("/api/routes/compare/", {"scenario": scenario["id"]}).json()

    assert all(r["hazards_on_route"] == [] for r in body["routes"])


@pytest.mark.django_db
def test_compare_unknown_scenario_is_404(client):
    response = client.get("/api/routes/compare/", {"scenario": "nope"})

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not found.", "fields": {}}
    }


@pytest.mark.django_db
def test_compare_missing_scenario_is_validation_error(client):
    response = client.get("/api/routes/compare/")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "scenario" in error["fields"]

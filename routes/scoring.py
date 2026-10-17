"""
Demo route comparison (E8 scenarios, E9 compare). Deterministic, no AI.

The scenarios and their route geometry live in `routes/data/demo_routes.json`. The polylines
were generated ONCE from the public OSRM bike router (routing.openstreetmap.de, OpenStreetMap
data), so they follow real streets; an API request never calls that router.

Each route is scored live against the current hazard reports:

    score = 100
            - per active hazard within 25 m:  CONDITION_PENALTY[condition] * freshness_weight
                        (same-type reports within 20 m of each other count once)
            - length:   0.5 point per % longer than the shortest alternative (max 20)
            - bike infrastructure: up to 15 points for the share NOT on a bike lane / shared path
                        (reports/data/skopje_bike.geojson, the same OSM data as E7)
    clamped to 0..100.

`condition` is the worst condition of the reports on the route, else green. Resolved reports and
reports with hazard_type "none" are ignored.
"""

from __future__ import annotations

import json
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any

from django.utils import timezone

from reports.bike import (
    CONDITION_RANK,
    HAZARD_NEAR_SEGMENT_M,
    _dataset,
    bboxes_overlap,
    coords_bbox,
    haversine_m,
    line_length_m,
    point_to_line_m,
)
from reports.choices import Condition, HazardType, SegmentKind, VerificationStatus
from reports.condition import compute_condition, compute_freshness
from reports.models import Report

DATA_PATH = Path(__file__).resolve().parent / "data" / "demo_routes.json"

HAZARD_NEAR_ROUTE_M = HAZARD_NEAR_SEGMENT_M  # 25 m, same rule as E7 segments

CONDITION_PENALTY = {
    Condition.RED: 20,
    Condition.AMBER: 10,
    Condition.GREY: 3,
    Condition.GREEN: 0,
}
# Reports of the same hazard type this close together are one hazard reported several times.
DUPLICATE_WITHIN_M = 20
LENGTH_PENALTY_PER_PERCENT = 0.5
MAX_LENGTH_PENALTY = 20
NO_BIKE_INFRA_PENALTY = 15
# A route point this close to a bike lane / shared path counts as "on" it.
ON_BIKE_INFRA_M = 12
BIKE_INFRA_KINDS = frozenset({SegmentKind.BIKE_LANE, SegmentKind.SHARED_PATH})


# --- Data ------------------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _scenarios() -> tuple[dict[str, Any], ...]:
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return tuple(raw["scenarios"])


def _scenario_summary(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "from": scenario["from"],
        "to": scenario["to"],
    }


def list_scenarios() -> dict[str, Any]:
    """Contract E8."""
    return {"scenarios": [_scenario_summary(s) for s in _scenarios()]}


def get_scenario(scenario_id: str) -> dict[str, Any] | None:
    return next((s for s in _scenarios() if s["id"] == scenario_id), None)


def _active_reports(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    """Unresolved reports inside `bbox` (padded a little), with condition and freshness now."""
    pad = 0.0005  # ~50 m, wider than HAZARD_NEAR_ROUTE_M
    min_lng, min_lat, max_lng, max_lat = bbox
    reports = (
        Report.objects.filter(
            lng__gte=min_lng - pad,
            lng__lte=max_lng + pad,
            lat__gte=min_lat - pad,
            lat__lte=max_lat + pad,
        )
        .exclude(verification_status=VerificationStatus.RESOLVED)
        .exclude(hazard_type=HazardType.NONE)
    )
    now = timezone.now()
    return [
        {
            "id": report.pk,
            "lng": report.lng,
            "lat": report.lat,
            "hazard_type": report.hazard_type,
            "condition": compute_condition(report, now),
            "freshness_weight": compute_freshness(report, now),
        }
        for report in reports
    ]


# --- Scoring ---------------------------------------------------------------------------------


def bike_infra_share(coordinates: list[list[float]]) -> float:
    """0..1: share of the route's length whose both ends lie near a bike lane or shared path."""
    lanes = [
        feature["geometry"]["coordinates"]
        for feature in _dataset()["lanes"]
        if feature.get("properties", {}).get("kind") in BIKE_INFRA_KINDS
        and bboxes_overlap(
            coords_bbox(feature["geometry"]["coordinates"]), coords_bbox(coordinates)
        )
    ]
    if not lanes:
        return 0.0

    def on_infra(point):
        return any(point_to_line_m(tuple(point), lane) <= ON_BIKE_INFRA_M for lane in lanes)

    flags = [on_infra(point) for point in coordinates]
    total = covered = 0.0
    for (a, b), (fa, fb) in zip(pairwise(coordinates), pairwise(flags), strict=True):
        step = haversine_m(tuple(a), tuple(b))
        total += step
        if fa and fb:
            covered += step
    return covered / total if total else 0.0


def distinct_hazards(reports: list[dict]) -> list[dict]:
    """Collapse duplicate reports (same type, within DUPLICATE_WITHIN_M); keep the worst one."""
    ordered = sorted(
        reports,
        key=lambda r: (-CONDITION_RANK.get(r["condition"], 0), -r["freshness_weight"], r["id"]),
    )
    kept: list[dict] = []
    for report in ordered:
        point = (report["lng"], report["lat"])
        if not any(
            k["hazard_type"] == report["hazard_type"]
            and haversine_m(point, (k["lng"], k["lat"])) <= DUPLICATE_WITHIN_M
            for k in kept
        ):
            kept.append(report)
    return kept


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _explain(route: dict, hazards: list[dict], length_m: int, shortest_m: int, share: float):
    lines = []
    labels = dict(HazardType.choices)
    real = [h for h in hazards if h["condition"] in (Condition.RED, Condition.AMBER)]
    grey = [h for h in hazards if h["condition"] == Condition.GREY]
    if real:
        kinds = sorted({labels.get(h["hazard_type"], "Other").lower() for h in real})
        lines.append(f"{_plural(len(real), 'recent hazard')} reported: {', '.join(kinds)}")
    elif grey:
        lines.append(f"No fresh hazards, {_plural(len(grey), 'old or unverified report')}")
    else:
        lines.append("No fresh hazards reported")
    if route.get("note"):
        lines.append(route["note"])
    if share >= 0.1:
        lines.append(f"{round(share * 100)}% on bike lanes or shared paths")
    if length_m <= shortest_m:
        lines.append("Shortest option")
    else:
        lines.append(f"{round((length_m / shortest_m - 1) * 100)}% longer than the shortest")
    return lines


def score_route(
    coordinates: list[list[float]], reports: list[dict], shortest_m: int
) -> dict[str, Any]:
    """Score, condition, hazard ids and the numbers behind them for one route geometry."""
    length_m = round(line_length_m(coordinates))
    on_route = [
        r
        for r in reports
        if point_to_line_m((r["lng"], r["lat"]), coordinates) <= HAZARD_NEAR_ROUTE_M
    ]
    distinct = distinct_hazards(on_route)
    hazard_penalty = sum(
        CONDITION_PENALTY.get(r["condition"], 0) * r["freshness_weight"] for r in distinct
    )
    longer_pct = max(0.0, (length_m / shortest_m - 1) * 100) if shortest_m else 0.0
    length_penalty = min(MAX_LENGTH_PENALTY, longer_pct * LENGTH_PENALTY_PER_PERCENT)
    share = bike_infra_share(coordinates)
    infra_penalty = NO_BIKE_INFRA_PENALTY * (1 - share)

    score = round(100 - hazard_penalty - length_penalty - infra_penalty)
    conditions = [r["condition"] for r in on_route]
    condition = (
        max(conditions, key=lambda c: CONDITION_RANK.get(c, 0)) if conditions else Condition.GREEN
    )
    return {
        "length_m": length_m,
        "score": max(0, min(100, score)),
        "condition": condition,
        "hazards": on_route,
        "distinct_hazards": distinct,
        "bike_share": share,
    }


def compare(scenario: dict[str, Any]) -> dict[str, Any]:
    """Contract E9: scored alternatives, best first."""
    all_coords = [c for route in scenario["routes"] for c in route["coordinates"]]
    reports = _active_reports(coords_bbox(all_coords))
    shortest_m = min(round(line_length_m(r["coordinates"])) for r in scenario["routes"])

    routes = []
    for route in scenario["routes"]:
        result = score_route(route["coordinates"], reports, shortest_m)
        routes.append(
            {
                "id": route["id"],
                "name": route["name"],
                "geometry": {"type": "LineString", "coordinates": route["coordinates"]},
                "length_m": result["length_m"],
                "score": result["score"],
                "condition": result["condition"],
                "hazards_on_route": sorted(h["id"] for h in result["hazards"]),
                "explanation": _explain(
                    route,
                    result["distinct_hazards"],
                    result["length_m"],
                    shortest_m,
                    result["bike_share"],
                ),
            }
        )
    # Best first; on a tie the shorter route wins.
    routes.sort(key=lambda r: (-r["score"], r["length_m"]))
    return {
        "scenario": _scenario_summary(scenario),
        "recommended_route_id": routes[0]["id"],
        "routes": routes,
    }

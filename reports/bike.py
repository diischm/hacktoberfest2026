"""
Existing bike lanes and bicycle parking in Skopje, from OpenStreetMap (E7 and E10).

The data is downloaded once with `manage.py fetch_bike_data` (Overpass API — the query engine
behind overpass-turbo.eu) and committed as `reports/data/skopje_bike.geojson`, so an API request
never talks to Overpass and tests stay offline. Refresh it with `make bike-data`.

E7 (`GET /api/segments/`) returns the LineStrings, scored against the current hazard reports:
`condition` and `score` say how comfortable a segment is *right now*, exactly like reports
(reports/condition.py) — a "car in bike lane" report 10 m away makes its segment red.

E10 (`GET /api/bike-parking/`) returns the parking spots. Both are filtered by the same `bbox`
as E3, and GeoJSON coordinates are `[lng, lat]`.
"""

from __future__ import annotations

import json
import logging
import math
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any

from django.utils import timezone

from reports.choices import Condition, SegmentKind, VerificationStatus
from reports.condition import compute_condition
from reports.models import Report

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parent / "data" / "skopje_bike.geojson"

# A report this close to a segment counts as "on" that segment. 25 m is wider than a painted
# lane and narrower than a parallel street, so a hazard on the next street over doesn't count.
HAZARD_NEAR_SEGMENT_M = 25

# How much one nearby hazard takes off a segment's comfort score (0–100).
SCORE_PENALTY = {
    Condition.RED: 45,
    Condition.AMBER: 20,
    Condition.GREY: 10,
    Condition.GREEN: 0,
}

# Worst-first ordering: a red report always wins over an amber one.
CONDITION_RANK = {
    Condition.GREEN: 0,
    Condition.GREY: 1,
    Condition.AMBER: 2,
    Condition.RED: 3,
}

EARTH_RADIUS_M = 6371008.8
METERS_PER_DEGREE_LAT = 110574.0


# --- Geo helpers -----------------------------------------------------------------------------


def _meters(lng: float, lat: float) -> tuple[float, float]:
    """Local flat projection in meters (fine for the tens-of-meters distances used here)."""
    return (lng * 111320.0 * math.cos(math.radians(lat)), lat * METERS_PER_DEGREE_LAT)


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two `(lng, lat)` points, in meters."""
    lng1, lat1 = a
    lng2, lat2 = b
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def line_length_m(coordinates: list[list[float]]) -> float:
    """Length of a GeoJSON LineString in meters."""
    return sum(haversine_m(tuple(a), tuple(b)) for a, b in pairwise(coordinates))


def point_to_segment_m(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    """Distance from `point` to the line segment start–end. All three are `(lng, lat)`."""
    px, py = _meters(*point)
    ax, ay = _meters(*start)
    bx, by = _meters(*end)
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    # Clamp the projection of the point onto the line to the segment's ends.
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def point_to_line_m(point: tuple[float, float], coordinates: list[list[float]]) -> float:
    """Shortest distance from a point to a whole LineString, in meters."""
    return min(point_to_segment_m(point, tuple(a), tuple(b)) for a, b in pairwise(coordinates))


def coords_bbox(coordinates: list[list[float]]) -> tuple[float, float, float, float]:
    """`(min_lng, min_lat, max_lng, max_lat)` of a coordinate list."""
    lngs = [c[0] for c in coordinates]
    lats = [c[1] for c in coordinates]
    return (min(lngs), min(lats), max(lngs), max(lats))


def bboxes_overlap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


# --- Reading the committed extract ------------------------------------------------------------


@lru_cache(maxsize=1)
def _dataset() -> dict[str, Any]:
    """
    The GeoJSON written by `manage.py fetch_bike_data`, split into lanes and parking and cached
    for the life of the process (the file only changes when someone re-runs the command).
    """
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("Bike data file missing: %s (run `make bike-data`).", DATA_PATH)
        return {"lanes": (), "parking": (), "osm_timestamp": None}
    except (OSError, json.JSONDecodeError):
        logger.exception("Could not read the bike data file %s.", DATA_PATH)
        return {"lanes": (), "parking": (), "osm_timestamp": None}

    features = raw.get("features", [])
    lanes = tuple(f for f in features if f.get("geometry", {}).get("type") == "LineString")
    parking = tuple(f for f in features if f.get("geometry", {}).get("type") == "Point")
    return {
        "lanes": lanes,
        "parking": parking,
        "osm_timestamp": raw.get("osm_timestamp"),
        "attribution": raw.get("attribution"),
    }


def dataset_info() -> dict[str, Any]:
    """Counts and the OSM snapshot time, for the health/diagnostics path."""
    data = _dataset()
    return {
        "lanes": len(data["lanes"]),
        "parking": len(data["parking"]),
        "osm_timestamp": data.get("osm_timestamp"),
    }


# --- E7: bike segments ------------------------------------------------------------------------


def segment_kind_from_tags(tags: dict[str, str]) -> str:
    """
    Map OpenStreetMap tags to the contract's segment `kind`.

    - a cycleway, or any way with a `cycleway=lane|track|…` side tag -> bike_lane
    - a path/footway/track that bikes may use (`bicycle=designated`)   -> shared_path
    - an informal path                                                  -> informal_path
    - anything else (a way with `bicycle=yes`)                          -> road
    """
    highway = tags.get("highway", "")
    if tags.get("informal") == "yes":
        return SegmentKind.INFORMAL_PATH
    if highway == "cycleway":
        return SegmentKind.BIKE_LANE
    if any(tags.get(f"cycleway{side}") for side in ("", ":left", ":right", ":both")):
        return SegmentKind.BIKE_LANE
    if highway in {"path", "footway", "track", "pedestrian", "bridleway", "steps"}:
        return SegmentKind.SHARED_PATH
    return SegmentKind.ROAD


def _worst_condition(conditions: list[str]) -> str:
    if not conditions:
        return Condition.GREEN
    return max(conditions, key=lambda c: CONDITION_RANK.get(c, 0))


def _score_from_conditions(conditions: list[str]) -> int:
    penalty = sum(SCORE_PENALTY.get(c, 0) for c in conditions)
    return max(0, min(100, 100 - penalty))


def active_hazard_reports(bbox: tuple[float, float, float, float], limit: int) -> list[dict]:
    """
    Reports inside `bbox` that can affect a segment, as small dicts. Resolved reports are
    ignored: they no longer make a lane uncomfortable.
    """
    min_lng, min_lat, max_lng, max_lat = bbox
    reports = (
        Report.objects.filter(
            lng__gte=min_lng, lng__lte=max_lng, lat__gte=min_lat, lat__lte=max_lat
        )
        .exclude(verification_status=VerificationStatus.RESOLVED)
        .order_by("-created_at")[:limit]
    )
    now = timezone.now()
    return [
        {
            "id": report.pk,
            "lng": report.lng,
            "lat": report.lat,
            "condition": compute_condition(report, now),
        }
        for report in reports
    ]


def score_lane(coordinates: list[list[float]], hazards: list[dict]) -> tuple[str, int, list[int]]:
    """`(condition, score, hazard_report_ids)` for one lane's geometry."""
    nearby = [
        hazard
        for hazard in hazards
        if point_to_line_m((hazard["lng"], hazard["lat"]), coordinates) <= HAZARD_NEAR_SEGMENT_M
    ]
    conditions = [hazard["condition"] for hazard in nearby]
    return (
        _worst_condition(conditions),
        _score_from_conditions(conditions),
        sorted(hazard["id"] for hazard in nearby),
    )


def build_segments(
    bbox: tuple[float, float, float, float], max_hazards: int, max_features: int
) -> dict[str, Any]:
    """Contract E7: GeoJSON FeatureCollection of `LineString` segments inside `bbox`."""
    lanes = [
        feature
        for feature in _dataset()["lanes"]
        if bboxes_overlap(coords_bbox(feature["geometry"]["coordinates"]), bbox)
    ][:max_features]
    hazards = active_hazard_reports(bbox, max_hazards)

    features = []
    for feature in lanes:
        coordinates = feature["geometry"]["coordinates"]
        properties = feature.get("properties", {})
        condition, score, hazard_ids = score_lane(coordinates, hazards)
        features.append(
            {
                "type": "Feature",
                "id": properties["id"],
                "geometry": {"type": "LineString", "coordinates": coordinates},
                "properties": {
                    "id": properties["id"],
                    "name": properties.get("name", ""),
                    "kind": properties.get("kind", SegmentKind.ROAD),
                    "condition": condition,
                    "score": score,
                    "length_m": round(line_length_m(coordinates)),
                    "hazard_report_ids": hazard_ids,
                    "is_synthetic": False,  # real OSM geometry, not hand-drawn demo data
                },
            }
        )
    features.sort(key=lambda f: f["properties"]["id"])
    return {
        "type": "FeatureCollection",
        "osm_timestamp": _dataset().get("osm_timestamp"),
        "features": features,
    }


# --- E10: bicycle parking ---------------------------------------------------------------------


def build_bike_parking(
    bbox: tuple[float, float, float, float], max_features: int
) -> dict[str, Any]:
    """Contract E10: GeoJSON FeatureCollection of `Point` features (bicycle parking) in `bbox`."""
    features = []
    for feature in _dataset()["parking"]:
        lng, lat = feature["geometry"]["coordinates"]
        if not (bbox[0] <= lng <= bbox[2] and bbox[1] <= lat <= bbox[3]):
            continue
        properties = feature.get("properties", {})
        features.append(
            {
                "type": "Feature",
                "id": properties["id"],
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
                "properties": {
                    "id": properties["id"],
                    "name": properties.get("name", ""),
                    "capacity": properties.get("capacity"),
                    "covered": properties.get("covered"),
                    "parking": properties.get("parking", ""),
                    "access": properties.get("access", ""),
                },
            }
        )
        if len(features) >= max_features:
            break
    features.sort(key=lambda f: f["properties"]["id"])
    return {
        "type": "FeatureCollection",
        "osm_timestamp": _dataset().get("osm_timestamp"),
        "features": features,
    }

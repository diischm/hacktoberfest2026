"""
`python manage.py fetch_bike_data`: download the existing bike lanes and bicycle parking in
Skopje and save them as a GeoJSON file that the API serves.

Data source: OpenStreetMap, through the **Overpass API** — the same "query engine" behind
<https://overpass-turbo.eu>. The download runs here, once, by hand; the result is committed to
`reports/data/skopje_bike.geojson`, so `GET /api/segments/` (E7) and `GET /api/bike-parking/`
(E10) read a local file and tests never touch the network.

Refresh the data (needs internet, takes a few seconds):

    make bike-data
    # or: .venv/bin/python manage.py fetch_bike_data

Re-run the normalization on a saved Overpass answer, without the network:

    .venv/bin/python manage.py fetch_bike_data --from-file raw-overpass.json

The Overpass answer is ODbL: the map must credit "© OpenStreetMap contributors".
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from django.core.management.base import BaseCommand, CommandError

from reports.bike import DATA_PATH, segment_kind_from_tags

# Overpass Query Language (QL). `{bbox}` is filled in as "south,west,north,east" (Overpass order,
# unlike the API's lng-first `bbox`). Positive value lists are used instead of `["cycleway"!~"^$"]`:
# a negative filter matches every way that merely lacks the tag (tens of thousands here).
OVERPASS_QUERY = """
[out:json][timeout:{timeout}];
(
  way["highway"="cycleway"]({bbox});
  way["cycleway"~"^(lane|track|shared_lane|share_busway|opposite|opposite_lane|opposite_track|separate|yes)$"]({bbox});
  way["cycleway:left"~"^(lane|track|shared_lane|share_busway|opposite_lane|opposite_track|separate|yes)$"]({bbox});
  way["cycleway:right"~"^(lane|track|shared_lane|share_busway|opposite_lane|opposite_track|separate|yes)$"]({bbox});
  way["cycleway:both"~"^(lane|track|shared_lane|share_busway|yes)$"]({bbox});
  way["highway"~"^(path|footway|track|pedestrian|bridleway|cycleway)$"]["bicycle"~"^(designated|yes)$"]({bbox});
  node["amenity"="bicycle_parking"]({bbox});
  way["amenity"="bicycle_parking"]({bbox});
);
out geom;
"""

# Overpass requires a descriptive User-Agent; the default httpx/urllib one gets HTTP 406.
USER_AGENT = (
    "BikeAble/1.0 (Skopje hackathon prototype; +https://github.com/diischm/hacktoberfest2026)"
)

# Public Overpass instances, tried in order. overpass-api.de is the main one; the others are
# fallbacks for when it is busy (they all serve the same OpenStreetMap data).
MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)

# Skopje and its surroundings: south,west,north,east for Overpass (the API uses lng-first).
DEFAULT_BBOX = "41.93,21.27,42.07,21.57"

# Coordinates are rounded to 6 decimals (~0.1 m) to keep the committed file small.
COORD_DECIMALS = 6

ATTRIBUTION = "© OpenStreetMap contributors, ODbL 1.0 — via Overpass API"


def build_query(bbox: str, timeout: int) -> str:
    return OVERPASS_QUERY.format(bbox=bbox, timeout=timeout).strip()


def _name(tags: dict) -> str:
    # Prefer a local name; fall back to the romanized/English one, then the international one.
    for key in ("name", "name:en", "int_name"):
        if tags.get(key):
            return tags[key]
    return ""


def _capacity(tags: dict) -> int | None:
    try:
        return int(tags["capacity"])
    except (KeyError, ValueError):
        return None


def _covered(tags: dict) -> bool | None:
    value = tags.get("covered")
    if value in ("yes", "true", "1"):
        return True
    if value in ("no", "false", "0"):
        return False
    return None


def _round(value: float) -> float:
    return round(float(value), COORD_DECIMALS)


def _dedupe(coordinates: list[list[float]]) -> list[list[float]]:
    """Drop consecutive identical points (a LineString needs distinct points, not zeros)."""
    out: list[list[float]] = []
    for point in coordinates:
        if not out or point != out[-1]:
            out.append(point)
    return out


def _feature(osm_id: int, geometry_type: str, coordinates, properties: dict) -> dict:
    return {
        "type": "Feature",
        "id": osm_id,
        "geometry": {"type": geometry_type, "coordinates": coordinates},
        "properties": properties,
    }


def _parking_point(element: dict) -> list[float] | None:
    """`[lng, lat]` for a bicycle-parking node, or the center of a parking area (way)."""
    if element.get("type") == "node" and "lat" in element and "lon" in element:
        return [_round(element["lon"]), _round(element["lat"])]
    geometry = element.get("geometry") or []
    if not geometry:
        return None
    lngs = [_round(g["lon"]) for g in geometry]
    lats = [_round(g["lat"]) for g in geometry]
    return [sum(lngs) / len(lngs), sum(lats) / len(lats)]


def normalize(raw: dict) -> dict:
    """
    Turn a raw Overpass JSON answer into the GeoJSON FeatureCollection we commit.

    Each `way` becomes a `LineString` bike segment, each bicycle-parking `node`/`way` a `Point`.
    Output is sorted by OSM id so re-running the command produces a stable, diff-friendly file.
    """
    lanes: list[dict] = []
    parking: list[dict] = []

    for element in raw.get("elements", []):
        tags = element.get("tags") or {}
        osm_id = element["id"]

        if tags.get("amenity") == "bicycle_parking":
            coordinates = _parking_point(element)
            if coordinates is None:
                continue
            parking.append(
                _feature(
                    osm_id,
                    "Point",
                    coordinates,
                    {
                        "id": osm_id,
                        "name": _name(tags),
                        "capacity": _capacity(tags),
                        "covered": _covered(tags),
                        "parking": tags.get("parking", ""),
                        "access": tags.get("access", ""),
                    },
                )
            )
            continue

        if element.get("type") != "way":
            continue  # only bicycle_parking nodes are interesting on their own
        points = [(g["lon"], g["lat"]) for g in element.get("geometry") or []]
        coordinates = _dedupe([[_round(lng), _round(lat)] for lng, lat in points])
        if len(coordinates) < 2:
            continue
        lanes.append(
            _feature(
                osm_id,
                "LineString",
                coordinates,
                {
                    "id": osm_id,
                    "name": _name(tags),
                    "kind": str(segment_kind_from_tags(tags)),
                },
            )
        )

    features = sorted(lanes, key=lambda f: f["id"]) + sorted(parking, key=lambda f: f["id"])
    return {
        "type": "FeatureCollection",
        "osm_timestamp": (raw.get("osm3s") or {}).get("timestamp_osm_base"),
        "attribution": ATTRIBUTION,
        "source": "https://overpass-api.de/api/interpreter",
        "features": features,
    }


class Command(BaseCommand):
    help = "Download existing bike lanes and bicycle parking in Skopje (Overpass API) as GeoJSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "--out",
            default=str(DATA_PATH),
            help=f"Where to write the GeoJSON (default: {DATA_PATH}).",
        )
        parser.add_argument(
            "--bbox",
            default=DEFAULT_BBOX,
            help=f"Overpass bbox as south,west,north,east (default: {DEFAULT_BBOX}).",
        )
        parser.add_argument(
            "--mirror",
            help="Use only this Overpass endpoint (default: try the built-in mirrors in order).",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=120,
            help="Overpass query timeout in seconds, also the HTTP timeout (default: 120).",
        )
        parser.add_argument(
            "--from-file",
            help="Read a saved Overpass JSON answer instead of calling the network.",
        )

    def handle(self, *args, **options):
        if options["from_file"]:
            raw = self._read_file(Path(options["from_file"]))
        else:
            raw = self._download(options["bbox"], options["timeout"], options["mirror"])

        data = normalize(raw)
        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        # One compact line (keeps the committed file small) plus a trailing newline.
        out.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        lanes = sum(1 for f in data["features"] if f["geometry"]["type"] == "LineString")
        parking = sum(1 for f in data["features"] if f["geometry"]["type"] == "Point")
        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {lanes} bike lanes and {parking} bike-parking spots to {out}\n"
                f"OSM snapshot: {data['osm_timestamp']}"
            )
        )

    def _read_file(self, path: Path) -> dict:
        if not path.is_file():
            raise CommandError(f"File not found: {path}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read {path}: {exc}") from exc

    def _download(self, bbox: str, timeout: int, mirror: str | None) -> dict:
        query = build_query(bbox, timeout)
        mirrors = (mirror,) if mirror else MIRRORS
        errors = []
        for url in mirrors:
            try:
                self.stdout.write(f"Querying {url} …")
                response = httpx.post(
                    url,
                    data={"data": query},
                    headers={"User-Agent": USER_AGENT},
                    timeout=timeout,
                )
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:  # ValueError covers a non-JSON answer
                errors.append(f"{url}: {exc}")
                self.stderr.write(self.style.WARNING(f"  failed: {exc}"))
        raise CommandError("All Overpass mirrors failed:\n  " + "\n  ".join(errors))

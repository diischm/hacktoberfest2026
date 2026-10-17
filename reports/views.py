"""
Read-only report API: E2 meta, E3 list (GeoJSON), E4 detail.

`APIView` is DRF's class-based view: a `get()` method handles GET, other methods get a 405.
Errors are raised as exceptions and turned into the contract shape by config/exceptions.py.
"""

import math

from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from config.exceptions import InvalidBBox
from reports.choices import VerificationStatus
from reports.limits import MAP_BOUNDS, MAX_REPORTS_PER_LIST
from reports.meta import build_meta
from reports.models import Report
from reports.serializers import ReportSerializer


class PublicReadView(APIView):
    # Anonymous read-only endpoints: no login, no session lookup.
    authentication_classes = ()
    permission_classes = (AllowAny,)


def parse_bbox(raw):
    """'minLng,minLat,maxLng,maxLat' -> (min_lng, min_lat, max_lng, max_lat), or InvalidBBox."""
    if raw is None:
        return (
            MAP_BOUNDS["min_lng"],
            MAP_BOUNDS["min_lat"],
            MAP_BOUNDS["max_lng"],
            MAP_BOUNDS["max_lat"],
        )
    parts = raw.split(",")
    if len(parts) != 4:
        raise InvalidBBox()
    try:
        min_lng, min_lat, max_lng, max_lat = (float(p) for p in parts)
    except ValueError:
        raise InvalidBBox() from None
    values = (min_lng, min_lat, max_lng, max_lat)
    if not all(math.isfinite(v) for v in values):
        raise InvalidBBox()
    if not (-180 <= min_lng <= 180 and -180 <= max_lng <= 180):
        raise InvalidBBox("bbox longitudes must be between -180 and 180.")
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise InvalidBBox("bbox latitudes must be between -90 and 90.")
    if min_lng > max_lng or min_lat > max_lat:
        raise InvalidBBox("bbox min values must not be greater than max values.")
    return values


def parse_bool(raw, name, default):
    if raw is None:
        return default
    if raw in ("true", "false"):
        return raw == "true"
    raise ValidationError({name: ["Must be true or false."]})


def report_feature(data):
    """Flat report dict -> GeoJSON Feature. GeoJSON order is [lng, lat]!"""
    properties = {k: v for k, v in data.items() if k not in ("lat", "lng")}
    return {
        "type": "Feature",
        "id": data["id"],
        "geometry": {"type": "Point", "coordinates": [data["lng"], data["lat"]]},
        "properties": properties,
    }


class MetaView(PublicReadView):
    def get(self, request):
        return Response(build_meta())


class ReportListView(PublicReadView):
    def get(self, request):
        min_lng, min_lat, max_lng, max_lat = parse_bbox(request.query_params.get("bbox"))
        include_resolved = parse_bool(
            request.query_params.get("include_resolved"), "include_resolved", default=False
        )

        reports = Report.objects.filter(
            lng__gte=min_lng, lng__lte=max_lng, lat__gte=min_lat, lat__lte=max_lat
        )
        if not include_resolved:
            reports = reports.exclude(verification_status=VerificationStatus.RESOLVED)
        # Fetch one extra row: if it exists, more than the limit matched.
        reports = list(
            reports.with_feedback_counts().order_by("-created_at", "-id")[
                : MAX_REPORTS_PER_LIST + 1
            ]
        )
        truncated = len(reports) > MAX_REPORTS_PER_LIST
        data = ReportSerializer(reports[:MAX_REPORTS_PER_LIST], many=True).data

        return Response(
            {
                "type": "FeatureCollection",
                "truncated": truncated,
                "features": [report_feature(item) for item in data],
            }
        )


class ReportDetailView(PublicReadView):
    def get(self, request, pk):
        # pk comes in as text so /api/reports/abc/ is a JSON 404, not Django's HTML 404 page.
        if not pk.isdigit():
            raise NotFound()
        report = Report.objects.with_feedback_counts().filter(pk=int(pk)).first()
        if report is None:
            raise NotFound()
        return Response(ReportSerializer(report).data)

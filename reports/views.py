"""
Report API: E2 meta, E3 list (GeoJSON), E4 detail, E5 create.

`APIView` is DRF's class-based view: a `get()` method handles GET, `post()` handles POST, other
methods get a 405. Errors are raised as exceptions and turned into the contract shape by
config/exceptions.py.
"""

import logging
import math
import uuid

from django.core.files.base import ContentFile
from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ai.errors import AiRateLimited, AiUnavailable
from ai.service import analyze_image
from config.exceptions import AiRateLimitedError, InvalidBBox
from reports.choices import HazardType, VerificationStatus
from reports.limits import MAP_BOUNDS, MAX_REPORTS_PER_LIST
from reports.meta import build_meta
from reports.models import Report
from reports.permissions import CsrfForUnsafeMethods
from reports.serializers import ReportSerializer, ReportUploadSerializer
from reports.throttles import ReportUploadThrottle

logger = logging.getLogger(__name__)


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
    """GET = E3 list, POST = E5 create (same URL)."""

    # POST: CSRF is checked even though users are anonymous (see reports/permissions.py).
    # GET is a "safe" method, so it passes this check untouched.
    permission_classes = (CsrfForUnsafeMethods,)

    # How the request body is read ("parsed") into request.data is left at DRF's default:
    # JSON, form and multipart. E5 sends multipart/form-data (text fields + a file); the file
    # ends up in request.data["photo"] as an UploadedFile.

    def get_throttles(self):
        # Only uploads are limited; reading the map stays unlimited.
        return [ReportUploadThrottle()] if self.request.method == "POST" else []

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

    def post(self, request):
        upload = ReportUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        data = upload.validated_data
        jpeg = data["photo_jpeg"]

        # Make sure this browser has a session (cookie "sessionid"), so the feedback endpoint can
        # later recognise "the same browser" by its session key.
        if request.session.session_key is None:
            request.session.create()

        report = Report(lat=data["lat"], lng=data["lng"], note=data["note"])
        try:
            result = analyze_image(jpeg, "image/jpeg", prepared=True)
        except AiRateLimited as exc:
            # Nothing has been written yet: no row, no file.
            raise AiRateLimitedError(exc.retry_after_seconds) from None
        except AiUnavailable as exc:
            # Contract: AI failure still creates the report, flagged for review.
            report.hazard_type = HazardType.OTHER
            report.description = ""
            report.ai_confidence = None
            report.needs_review = True
            report.verification_status = VerificationStatus.AI_FLAGGED
            # exc.reason is a short fixed string written by us (ai/errors.py), safe to store.
            report.ai_raw_response = {"error": exc.reason, "response": exc.raw_response}
        else:
            report.hazard_type = result.hazard_type
            report.description = result.description
            report.ai_confidence = result.confidence
            report.needs_review = result.needs_review
            report.verification_status = (
                VerificationStatus.AI_FLAGGED
                if result.needs_review
                else VerificationStatus.UNVERIFIED
            )
            report.ai_raw_response = result.raw_response

        _save_with_photo(report, jpeg)
        return Response(ReportSerializer(report).data, status=status.HTTP_201_CREATED)


def _save_with_photo(report, jpeg):
    """
    Write the photo file, then the database row. If the row fails, delete the file again, so no
    orphan photo is left on disk.

    `transaction.atomic()` means "all database writes in this block happen, or none do". There is
    only one write today, but it keeps the rule true if more are added (e.g. an audit row).
    The file system isn't part of the transaction, hence the manual delete.
    """
    # Random name: doesn't reveal the report id or the upload order. upload_to on the model adds
    # the dated folder: reports/<year>/<month>/<uuid>.jpg
    report.photo.save(f"{uuid.uuid4().hex}.jpg", ContentFile(jpeg), save=False)
    try:
        with transaction.atomic():
            report.save()
    except Exception:
        report.photo.delete(save=False)
        logger.error("Saving a new report failed; removed its photo file.")
        raise


class ReportDetailView(PublicReadView):
    def get(self, request, pk):
        # pk comes in as text so /api/reports/abc/ is a JSON 404, not Django's HTML 404 page.
        if not pk.isdigit():
            raise NotFound()
        report = Report.objects.with_feedback_counts().filter(pk=int(pk)).first()
        if report is None:
            raise NotFound()
        return Response(ReportSerializer(report).data)

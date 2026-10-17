"""
Report -> JSON, exactly the "Report object" in docs/plan/API_CONTRACT.md.

A DRF *serializer* converts model instances to plain dicts (and, for input, validates data).
`SerializerMethodField` means "call get_<name>() to compute this value".
"""

from django.utils import timezone
from rest_framework import serializers

from ai.errors import AiUnavailable
from ai.image import detect_mime_type, prepare_image
from config.exceptions import PhotoTooLarge, UnsupportedPhotoType
from reports import limits
from reports.condition import compute_condition, compute_freshness
from reports.models import Report

COORD_DECIMALS = 6


class ReportSerializer(serializers.ModelSerializer):
    lat = serializers.SerializerMethodField()
    lng = serializers.SerializerMethodField()
    condition = serializers.SerializerMethodField()
    freshness_weight = serializers.SerializerMethodField()
    last_confirmed_at = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    feedback_counts = serializers.SerializerMethodField()

    class Meta:
        model = Report
        # Explicit allow-list: ai_raw_response, resolved_at, photo (the raw path) and feedback
        # session keys are never sent.
        fields = (
            "id",
            "lat",
            "lng",
            "hazard_type",
            "description",
            "note",
            "ai_confidence",
            "needs_review",
            "verification_status",
            "condition",
            "freshness_weight",
            "created_at",
            "last_confirmed_at",
            "photo_url",
            "is_synthetic",
            "feedback_counts",
        )

    def _now(self):
        # One "now" per request, so all reports in a list are judged at the same moment.
        if "now" not in self.context:
            self.context["now"] = timezone.now()
        return self.context["now"]

    def get_lat(self, obj):
        return round(obj.lat, COORD_DECIMALS)

    def get_lng(self, obj):
        return round(obj.lng, COORD_DECIMALS)

    def get_condition(self, obj):
        return compute_condition(obj, self._now())

    def get_freshness_weight(self, obj):
        return compute_freshness(obj, self._now())

    def get_last_confirmed_at(self, obj):
        # Contract: equals created_at until someone sends still_there.
        value = obj.last_confirmed_at or obj.created_at
        return self.fields["created_at"].to_representation(value)

    def get_photo_url(self, obj):
        # Root-relative ("/media/reports/..."), exactly like the contract example.
        return obj.photo.url if obj.photo else None

    def get_feedback_counts(self, obj):
        return obj.feedback_counts


class ReportUploadSerializer(serializers.Serializer):
    """
    Input for POST /api/reports/ (E5). Used only to validate; the response is ReportSerializer.

    Photo problems are not 400s: too large -> 413, not a JPEG/PNG/WebP -> 415 (contract). Those
    are raised as their own exceptions, which DRF lets through is_valid() instead of collecting
    them as field errors.
    """

    photo = serializers.FileField()
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    note = serializers.CharField(
        required=False, allow_blank=True, max_length=limits.MAX_NOTE_LENGTH, default=""
    )

    def validate_photo(self, photo):
        if photo.size > limits.MAX_PHOTO_BYTES:
            raise PhotoTooLarge()
        if detect_mime_type(photo.read()) not in limits.ACCEPTED_PHOTO_TYPES:
            raise UnsupportedPhotoType()
        return photo

    def validate_lat(self, value):
        bounds = limits.MAP_BOUNDS
        if not bounds["min_lat"] <= value <= bounds["max_lat"]:
            raise serializers.ValidationError("Location is outside the map area.")
        return value

    def validate_lng(self, value):
        bounds = limits.MAP_BOUNDS
        if not bounds["min_lng"] <= value <= bounds["max_lng"]:
            raise serializers.ValidationError("Location is outside the map area.")
        return value

    def validate(self, attrs):
        # Only reached when every field is valid, so a bad lat doesn't cost an image resize.
        # This JPEG (no EXIF/GPS, resized) is what Gemini sees AND what we store: the original
        # upload bytes are never saved.
        attrs["photo"].seek(0)
        try:
            attrs["photo_jpeg"] = prepare_image(attrs["photo"].read())
        except AiUnavailable:  # Pillow could read the header but not the pixels
            raise UnsupportedPhotoType() from None
        return attrs

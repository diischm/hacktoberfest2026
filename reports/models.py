from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Count
from django.utils import timezone

from reports.choices import FeedbackAction, HazardType, VerificationStatus


class Report(models.Model):
    """
    One hazard photo reported by a cyclist.

    Only stored fields live here. `condition` and `freshness_weight` from the API contract are
    NOT stored: they depend on the current time, so they are computed on read
    (feat/freshness-verification).
    """

    # FloatField, not DecimalField: the contract sends lat/lng as JSON numbers (DRF turns
    # Decimals into strings by default), 6 decimals is ~0.1 m which a float holds easily, and
    # the backend plan uses plain floats for distance maths (no GIS libraries).
    lat = models.FloatField(validators=[MinValueValidator(-90), MaxValueValidator(90)])
    lng = models.FloatField(validators=[MinValueValidator(-180), MaxValueValidator(180)])

    hazard_type = models.CharField(
        max_length=32, choices=HazardType.choices, default=HazardType.OTHER
    )
    description = models.TextField(blank=True, default="", help_text="Written by the AI.")
    note = models.CharField(
        max_length=500, blank=True, default="", help_text="Optional note from the uploader."
    )
    # blank photo is allowed for seed/demo data; the API sends photo_url: null then.
    photo = models.ImageField(upload_to="reports/%Y/%m/", blank=True)

    ai_confidence = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text="0-1, empty if the AI failed or did not run.",
    )
    needs_review = models.BooleanField(default=False)
    verification_status = models.CharField(
        max_length=32, choices=VerificationStatus.choices, default=VerificationStatus.UNVERIFIED
    )
    is_synthetic = models.BooleanField(default=False, help_text="Demo data, labelled in the UI.")
    # Full Gemini answer, kept for debugging only. Never exposed by the API.
    ai_raw_response = models.JSONField(null=True, blank=True)

    # default=timezone.now (not auto_now_add) so fixtures and the seed command can set old dates.
    created_at = models.DateTimeField(default=timezone.now)
    last_confirmed_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = (
            models.Index(fields=["created_at"], name="report_created_at_idx"),
            # Speeds up bbox queries (lat BETWEEN .. AND lng BETWEEN ..) in E3.
            models.Index(fields=["lat", "lng"], name="report_lat_lng_idx"),
        )

    def __str__(self):
        return f"#{self.pk} {self.get_hazard_type_display()} ({self.get_verification_status_display()})"

    @property
    def feedback_counts(self) -> dict[str, int]:
        """{"still_there": n, "resolved": n, "dispute": n}, zeros included. One query."""
        counts = {action: 0 for action in FeedbackAction.values}
        rows = self.feedback.values("action").annotate(n=Count("id"))
        for row in rows:
            counts[row["action"]] = row["n"]
        return counts


class ReportFeedback(models.Model):
    """One rider's "still there / it's gone / not accurate" vote on a report."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="feedback")
    action = models.CharField(max_length=16, choices=FeedbackAction.choices)
    # Anonymous users: the Django session key identifies "the same browser" (40 = Django's max).
    session_key = models.CharField(max_length=40)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-created_at",)
        constraints = (
            # Backs the contract's 409 duplicate_feedback rule at database level.
            models.UniqueConstraint(
                fields=["report", "session_key", "action"],
                name="unique_feedback_per_session_action",
            ),
        )

    def __str__(self):
        return f"{self.action} on report #{self.report_id}"

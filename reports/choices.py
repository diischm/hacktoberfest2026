"""
Enum values shared by models, admin and (later) the API.

The keys must match docs/plan/API_CONTRACT.md exactly; the labels match GET /api/meta/ (E2).
`TextChoices` is Django's enum type: the first value is what the database stores, the second is
the human-readable label shown in the admin.
"""

from django.db import models


class HazardType(models.TextChoices):
    ROAD_BLOCK = "road_block", "Road blocked"
    CAR_ON_SIDEWALK = "car_on_sidewalk", "Car on sidewalk"
    CAR_ON_CROSSWALK = "car_on_crosswalk", "Car on crosswalk"
    CAR_IN_BIKE_LANE = "car_in_bike_lane", "Car in bike lane"
    POTHOLE_DAMAGE = "pothole_damage", "Pothole / damage"
    CONSTRUCTION_DEBRIS = "construction_debris", "Construction debris"
    INFORMAL_SHORTCUT = "informal_shortcut", "Informal shortcut path"
    OTHER = "other", "Other"
    NONE = "none", "No hazard found"


class VerificationStatus(models.TextChoices):
    UNVERIFIED = "unverified", "Unverified"
    AI_FLAGGED = "ai_flagged", "Needs review"
    COMMUNITY_CONFIRMED = "community_confirmed", "Confirmed by riders"
    VERIFIED = "verified", "Verified"
    DISPUTED = "disputed", "Disputed"
    RESOLVED = "resolved", "Resolved"


class FeedbackAction(models.TextChoices):
    STILL_THERE = "still_there", "Still there"
    RESOLVED = "resolved", "It's gone"
    DISPUTE = "dispute", "Not accurate"

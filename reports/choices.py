"""
Enum values shared by models, admin and the API (GET /api/meta/ is built from this file).

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


class Condition(models.TextChoices):
    """Map color of a report. Computed on read (reports/condition.py), never stored."""

    GREEN = "green", "Clear"
    AMBER = "amber", "Caution"
    RED = "red", "Hazard"
    GREY = "grey", "Unknown"


# Extra per-key data for /api/meta/. Tests check every enum key has an entry.
HAZARD_ICONS = {
    HazardType.ROAD_BLOCK: "barrier",
    HazardType.CAR_ON_SIDEWALK: "car",
    HazardType.CAR_ON_CROSSWALK: "car",
    HazardType.CAR_IN_BIKE_LANE: "car",
    HazardType.POTHOLE_DAMAGE: "pothole",
    HazardType.CONSTRUCTION_DEBRIS: "cone",
    HazardType.INFORMAL_SHORTCUT: "footpath",
    HazardType.OTHER: "warning",
    HazardType.NONE: "check",
}

# informal_shortcut is information, not a hazard; none means the AI saw nothing.
NOT_A_HAZARD = frozenset({HazardType.INFORMAL_SHORTCUT, HazardType.NONE})

CONDITION_HEX = {
    Condition.GREEN: "#2E7D32",
    Condition.AMBER: "#F9A825",
    Condition.RED: "#C62828",
    Condition.GREY: "#757575",
}

CONDITION_MEANINGS = {
    Condition.GREEN: "Clear / comfortable",
    Condition.AMBER: "Minor issue or aging report",
    Condition.RED: "Fresh, significant hazard",
    Condition.GREY: "Unknown, stale, disputed or needs review",
}

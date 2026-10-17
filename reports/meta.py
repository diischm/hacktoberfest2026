"""Builds the GET /api/meta/ (E2) body from reports/choices.py and reports/limits.py."""

from reports import limits
from reports.choices import (
    CONDITION_HEX,
    CONDITION_MEANINGS,
    HAZARD_ICONS,
    NOT_A_HAZARD,
    Condition,
    FeedbackAction,
    HazardType,
    VerificationStatus,
)

CONTRACT_VERSION = 1


def build_meta() -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "hazard_types": [
            {
                "key": h.value,
                "label": h.label,
                "icon": HAZARD_ICONS[h],
                "is_hazard": h not in NOT_A_HAZARD,
            }
            for h in HazardType
        ],
        "conditions": [
            {
                "key": c.value,
                "hex": CONDITION_HEX[c],
                "label": c.label,
                "meaning": CONDITION_MEANINGS[c],
            }
            for c in Condition
        ],
        "verification_statuses": [{"key": s.value, "label": s.label} for s in VerificationStatus],
        "feedback_actions": [{"key": a.value, "label": a.label} for a in FeedbackAction],
        "upload": {
            "max_photo_bytes": limits.MAX_PHOTO_BYTES,
            "accepted_types": list(limits.ACCEPTED_PHOTO_TYPES),
            "max_note_length": limits.MAX_NOTE_LENGTH,
        },
        "map": {
            "center": dict(limits.MAP_CENTER),
            "zoom": limits.MAP_ZOOM,
            "bounds": dict(limits.MAP_BOUNDS),
        },
    }

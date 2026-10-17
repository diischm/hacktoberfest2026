"""
Fake analysis for AI_MODE=mock: no network, no key, same photo -> same answer every time.

Set AI_MOCK_FORCE in .env to try the error paths without a real key:
  AI_MOCK_FORCE=rate_limited  -> raises AiRateLimited (upload answers 429)
  AI_MOCK_FORCE=unavailable   -> raises AiUnavailable (upload saves a "needs review" report)
"""

import hashlib
import logging

from ai.errors import AiRateLimited, AiUnavailable
from ai.schema import AnalysisResult

logger = logging.getLogger(__name__)

FORCE_RATE_LIMITED = "rate_limited"
FORCE_UNAVAILABLE = "unavailable"
MOCK_RETRY_AFTER_SECONDS = 60

# Plausible answers. One of them has low confidence, so the "needs review" state shows up too.
MOCK_ANSWERS = [
    {
        "hazard_type": "car_in_bike_lane",
        "description": "[MOCK] A silver car is parked across the painted bike lane.",
        "confidence": 0.91,
        "visible_evidence": ["painted bike lane", "parked car blocking the lane"],
    },
    {
        "hazard_type": "pothole_damage",
        "description": "[MOCK] A deep pothole breaks the asphalt near the curb.",
        "confidence": 0.84,
        "visible_evidence": ["pothole", "cracked asphalt"],
    },
    {
        "hazard_type": "car_on_crosswalk",
        "description": "[MOCK] A dark SUV is stopped on the zebra crossing.",
        "confidence": 0.87,
        "visible_evidence": ["zebra crossing", "car on the stripes"],
    },
    {
        "hazard_type": "construction_debris",
        "description": "[MOCK] Sand and broken bricks cover part of the cycle path.",
        "confidence": 0.78,
        "visible_evidence": ["sand pile", "broken bricks", "cycle path"],
    },
    {
        "hazard_type": "informal_shortcut",
        "description": "[MOCK] A worn dirt path cuts diagonally through the grass.",
        "confidence": 0.74,
        "visible_evidence": ["worn dirt path", "grass on both sides"],
    },
    {
        "hazard_type": "road_block",
        "description": "[MOCK] Something may be blocking the lane, but the photo is unclear.",
        "confidence": 0.45,
        "visible_evidence": ["blurry object in the lane"],
    },
]


def analyze(image_bytes: bytes, force: str = "") -> AnalysisResult:
    if force == FORCE_RATE_LIMITED:
        raise AiRateLimited(retry_after_seconds=MOCK_RETRY_AFTER_SECONDS)
    if force == FORCE_UNAVAILABLE:
        raise AiUnavailable("mock_forced_unavailable", raw_response={"mock": True})
    if force:
        logger.warning(
            "AI_MOCK_FORCE=%r is not %r or %r; ignoring it.",
            force,
            FORCE_RATE_LIMITED,
            FORCE_UNAVAILABLE,
        )

    index = int.from_bytes(hashlib.sha256(image_bytes).digest()[:4], "big") % len(MOCK_ANSWERS)
    result = AnalysisResult.model_validate(MOCK_ANSWERS[index])
    result.raw_response = {"mock": True, "mock_answer_index": index}
    return result

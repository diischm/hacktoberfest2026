"""
AnalysisResult: the checked shape of one photo analysis, plus the rules that decide needs_review.

Uses Pydantic, a library that turns "a dict that should look like X" into a typed object and
raises a ValidationError if it doesn't. We never trust the model's JSON: everything Gemini (or
the mock) answers goes through `parse_model_output` / `AnalysisResult.model_validate`.
"""

import json
import math

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from ai.errors import AiUnavailable
from reports.choices import HazardType

# --- Thresholds: the one place to tune them ---------------------------------------------
# Below this confidence a report is marked needs_review.
REVIEW_CONFIDENCE_THRESHOLD = 0.6
# These hazard types always need a human look.
ALWAYS_REVIEW_TYPES = frozenset({HazardType.OTHER})
MAX_DESCRIPTION_CHARS = 300
MAX_EVIDENCE_ITEMS = 5
MAX_EVIDENCE_CHARS = 80


class AnalysisResult(BaseModel):
    hazard_type: str  # always one of HazardType.values after validation
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_CHARS)
    confidence: float = Field(ge=0, le=1)
    visible_evidence: list[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_ITEMS)
    needs_review: bool = False
    # The model's full answer, for Report.ai_raw_response. Kept out of model_dump() / JSON.
    raw_response: dict | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="before")
    @classmethod
    def unknown_hazard_type_becomes_other(cls, data):
        # Runs before the field checks, so it can set needs_review too.
        if isinstance(data, dict):
            value = data.get("hazard_type")
            key = value.strip().lower() if isinstance(value, str) else value
            if key not in HazardType.values:
                data = {**data, "hazard_type": HazardType.OTHER, "needs_review": True}
            else:
                data = {**data, "hazard_type": key}
        return data

    @field_validator("description", mode="before")
    @classmethod
    def tidy_description(cls, value):
        if not isinstance(value, str):
            return value  # Pydantic rejects it
        text = " ".join(value.split())
        if len(text) > MAX_DESCRIPTION_CHARS:
            text = text[: MAX_DESCRIPTION_CHARS - 1].rstrip() + "…"
        return text

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, value):
        if isinstance(value, bool) or not isinstance(value, int | float) or math.isnan(value):
            raise ValueError("confidence must be a number")
        return min(max(float(value), 0.0), 1.0)

    @field_validator("visible_evidence", mode="before")
    @classmethod
    def tidy_evidence(cls, value):
        if not isinstance(value, list):
            return value  # Pydantic rejects it
        items = [" ".join(item.split()) for item in value if isinstance(item, str)]
        return [item[:MAX_EVIDENCE_CHARS] for item in items if item][:MAX_EVIDENCE_ITEMS]

    @model_validator(mode="after")
    def apply_review_rules(self):
        if self.confidence < REVIEW_CONFIDENCE_THRESHOLD or self.hazard_type in ALWAYS_REVIEW_TYPES:
            self.needs_review = True
        return self


def parse_model_output(text: str | None) -> AnalysisResult:
    """Turn the model's JSON text into an AnalysisResult, or raise AiUnavailable."""
    if not text:
        raise AiUnavailable("empty_answer")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise AiUnavailable("answer_not_json") from None
    if not isinstance(data, dict):
        raise AiUnavailable("answer_not_object")
    try:
        return AnalysisResult.model_validate(data)
    except ValidationError as exc:
        fields = sorted({str(err["loc"][0]) for err in exc.errors() if err["loc"]})
        raise AiUnavailable(f"answer_invalid: {', '.join(fields) or 'unknown'}") from None


# JSON Schema sent to Gemini ("structured output"): the API then only answers with JSON of
# this shape. We still validate it above, because a schema is a strong hint, not a guarantee.
GEMINI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "hazard_type": {"type": "string", "enum": list(HazardType.values)},
        "description": {"type": "string", "maxLength": MAX_DESCRIPTION_CHARS},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "visible_evidence": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": MAX_EVIDENCE_ITEMS,
        },
        "needs_review": {"type": "boolean"},
    },
    "required": ["hazard_type", "description", "confidence", "visible_evidence", "needs_review"],
    "propertyOrdering": [
        "hazard_type",
        "description",
        "confidence",
        "visible_evidence",
        "needs_review",
    ],
}

import json

import pytest

from ai.errors import AiUnavailable
from ai.prompt import CATEGORY_DEFINITIONS, SYSTEM_PROMPT
from ai.schema import (
    GEMINI_RESPONSE_SCHEMA,
    MAX_DESCRIPTION_CHARS,
    MAX_EVIDENCE_ITEMS,
    REVIEW_CONFIDENCE_THRESHOLD,
    AnalysisResult,
    parse_model_output,
)
from reports.choices import HazardType


def answer(**overrides):
    data = {
        "hazard_type": "pothole_damage",
        "description": "A deep pothole near the curb.",
        "confidence": 0.9,
        "visible_evidence": ["pothole"],
        "needs_review": False,
    }
    return {**data, **overrides}


def test_good_answer_passes_unchanged():
    result = AnalysisResult.model_validate(answer())
    assert result.hazard_type == "pothole_damage"
    assert result.needs_review is False


# --- needs_review rules ------------------------------------------------------------------


def test_low_confidence_needs_review():
    result = AnalysisResult.model_validate(answer(confidence=REVIEW_CONFIDENCE_THRESHOLD - 0.01))
    assert result.needs_review is True


def test_confidence_at_threshold_does_not_need_review():
    result = AnalysisResult.model_validate(answer(confidence=REVIEW_CONFIDENCE_THRESHOLD))
    assert result.needs_review is False


def test_other_always_needs_review():
    assert AnalysisResult.model_validate(answer(hazard_type="other")).needs_review is True


def test_model_saying_unsure_is_kept():
    assert AnalysisResult.model_validate(answer(needs_review=True)).needs_review is True


def test_none_with_high_confidence_is_fine():
    assert AnalysisResult.model_validate(answer(hazard_type="none")).needs_review is False


# --- cleaning and validation -------------------------------------------------------------


def test_unknown_hazard_type_becomes_other_and_needs_review():
    result = AnalysisResult.model_validate(answer(hazard_type="alien_spaceship"))
    assert result.hazard_type == "other"
    assert result.needs_review is True


def test_hazard_type_is_normalized():
    assert AnalysisResult.model_validate(answer(hazard_type=" Car_In_Bike_Lane ")).hazard_type == (
        "car_in_bike_lane"
    )


@pytest.mark.parametrize(("given", "expected"), [(1.7, 1.0), (-0.2, 0.0), (1, 1.0)])
def test_confidence_is_clamped(given, expected):
    assert AnalysisResult.model_validate(answer(confidence=given)).confidence == expected


@pytest.mark.parametrize("bad", ["high", None, True, float("nan")])
def test_confidence_must_be_a_number(bad):
    with pytest.raises(AiUnavailable, match="confidence"):
        parse_model_output(json.dumps(answer(confidence=bad), allow_nan=True))


def test_long_description_is_shortened():
    result = AnalysisResult.model_validate(answer(description="word " * 200))
    assert len(result.description) <= MAX_DESCRIPTION_CHARS


def test_evidence_is_trimmed_to_five_short_items():
    result = AnalysisResult.model_validate(answer(visible_evidence=["x" * 500, "", 3, *"abcdef"]))
    assert len(result.visible_evidence) == MAX_EVIDENCE_ITEMS
    assert all(0 < len(item) <= 80 for item in result.visible_evidence)


@pytest.mark.parametrize("description", ["", "   ", None])
def test_empty_description_is_unavailable(description):
    with pytest.raises(AiUnavailable, match="description"):
        parse_model_output(json.dumps(answer(description=description)))


@pytest.mark.parametrize("text", ["", None, "not json {", "[1, 2]", '"just a string"'])
def test_non_object_answers_are_unavailable(text):
    with pytest.raises(AiUnavailable):
        parse_model_output(text)


@pytest.mark.parametrize("field", ["hazard_type", "description", "confidence"])
def test_missing_required_field_is_unavailable_or_other(field):
    data = answer()
    del data[field]
    if field == "hazard_type":
        # Missing type is treated like an unknown one.
        result = parse_model_output(json.dumps(data))
        assert (result.hazard_type, result.needs_review) == ("other", True)
    else:
        with pytest.raises(AiUnavailable, match=field):
            parse_model_output(json.dumps(data))


def test_raw_response_is_not_part_of_the_dump():
    result = AnalysisResult.model_validate(answer())
    result.raw_response = {"big": "blob"}
    assert "raw_response" not in result.model_dump()


# --- prompt and schema stay in sync with the contract ------------------------------------


def test_prompt_categories_equal_hazard_types():
    assert list(CATEGORY_DEFINITIONS) == list(HazardType.values)
    for key in HazardType.values:
        assert f"- {key}:" in SYSTEM_PROMPT


def test_response_schema_enum_equals_hazard_types():
    assert GEMINI_RESPONSE_SCHEMA["properties"]["hazard_type"]["enum"] == list(HazardType.values)
    assert set(GEMINI_RESPONSE_SCHEMA["required"]) == set(AnalysisResult.model_fields) - {
        "raw_response"
    }

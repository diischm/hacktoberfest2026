import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction

from reports.choices import FeedbackAction, HazardType, VerificationStatus
from reports.models import Report, ReportFeedback

# Copied by hand from docs/plan/API_CONTRACT.md so that any drift between code and contract
# makes these tests fail. Change them only together with a contract change.
CONTRACT_HAZARD_TYPES = [
    "road_block",
    "car_on_sidewalk",
    "car_on_crosswalk",
    "car_in_bike_lane",
    "pothole_damage",
    "construction_debris",
    "informal_shortcut",
    "other",
    "none",
]
CONTRACT_VERIFICATION_STATUSES = [
    "unverified",
    "ai_flagged",
    "community_confirmed",
    "verified",
    "disputed",
    "resolved",
]
CONTRACT_FEEDBACK_ACTIONS = ["still_there", "resolved", "dispute"]


def make_report(**overrides):
    fields = {"lat": 41.9962, "lng": 21.4316, "hazard_type": HazardType.POTHOLE_DAMAGE}
    fields.update(overrides)
    return Report(**fields)


@pytest.mark.django_db
def test_create_report_with_defaults():
    report = make_report()
    report.full_clean()
    report.save()

    report.refresh_from_db()
    assert report.verification_status == VerificationStatus.UNVERIFIED
    assert report.needs_review is False
    assert report.is_synthetic is False
    assert report.note == ""
    assert report.description == ""
    assert report.ai_confidence is None
    assert report.ai_raw_response is None
    assert report.created_at is not None
    assert report.last_confirmed_at is None
    assert report.resolved_at is None
    assert not report.photo
    assert "Pothole" in str(report)


@pytest.mark.parametrize(
    "field, value",
    [
        ("lat", 90.1),
        ("lat", -90.1),
        ("lng", 180.1),
        ("lng", -180.1),
        ("ai_confidence", 1.01),
        ("ai_confidence", -0.01),
        ("hazard_type", "unicorn"),
        ("verification_status", "maybe"),
        pytest.param("note", "x" * 501, id="note-too-long"),
    ],
)
def test_full_clean_rejects_invalid_values(field, value):
    report = make_report(**{field: value})
    with pytest.raises(ValidationError) as exc:
        report.full_clean()
    assert field in exc.value.message_dict


@pytest.mark.parametrize("field, value", [("lat", 90), ("lng", -180), ("ai_confidence", 0)])
def test_full_clean_accepts_range_edges(field, value):
    make_report(**{field: value}).full_clean()


def test_choices_match_contract_exactly():
    assert HazardType.values == CONTRACT_HAZARD_TYPES
    assert VerificationStatus.values == CONTRACT_VERIFICATION_STATUSES
    assert FeedbackAction.values == CONTRACT_FEEDBACK_ACTIONS


def test_condition_and_freshness_are_not_stored():
    # They are computed on read in feat/freshness-verification.
    field_names = {f.name for f in Report._meta.get_fields()}
    assert "condition" not in field_names
    assert "freshness_weight" not in field_names


@pytest.mark.django_db
def test_duplicate_feedback_raises_integrity_error():
    report = make_report()
    report.save()
    ReportFeedback.objects.create(report=report, session_key="abc", action="still_there")

    with pytest.raises(IntegrityError), transaction.atomic():
        ReportFeedback.objects.create(report=report, session_key="abc", action="still_there")

    # Same session, different action: allowed.
    ReportFeedback.objects.create(report=report, session_key="abc", action="dispute")
    assert report.feedback.count() == 2


@pytest.mark.django_db
def test_feedback_counts():
    report = make_report()
    report.save()
    assert report.feedback_counts == {"still_there": 0, "resolved": 0, "dispute": 0}

    for session in ("s1", "s2", "s3"):
        ReportFeedback.objects.create(report=report, session_key=session, action="still_there")
    ReportFeedback.objects.create(report=report, session_key="s1", action="dispute")
    # Feedback on another report must not be counted.
    other = make_report()
    other.save()
    ReportFeedback.objects.create(report=other, session_key="s1", action="resolved")

    assert report.feedback_counts == {"still_there": 3, "resolved": 0, "dispute": 1}


@pytest.mark.django_db
def test_demo_fixture_loads_and_is_all_synthetic():
    call_command("loaddata", "demo_reports", verbosity=0)

    reports = list(Report.objects.all())
    assert 8 <= len(reports) <= 12
    assert all(r.is_synthetic for r in reports)
    assert all(r.description.startswith("[SYNTHETIC]") for r in reports)
    assert {r.hazard_type for r in reports} == set(CONTRACT_HAZARD_TYPES)
    for report in reports:
        report.full_clean()  # every fixture row passes model validation

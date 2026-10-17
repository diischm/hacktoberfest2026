from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from reports.choices import Condition, HazardType, VerificationStatus
from reports.condition import compute_condition, compute_freshness
from reports.models import Report

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=ZoneInfo("Europe/Skopje"))


def report(
    hazard="pothole_damage",
    status="unverified",
    age=timedelta(hours=1),
    confirmed=None,
    needs_review=False,
):
    return Report(
        needs_review=needs_review,
        lat=41.99,
        lng=21.43,
        hazard_type=hazard,
        verification_status=status,
        created_at=NOW - age,
        last_confirmed_at=None if confirmed is None else NOW - confirmed,
    )


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"status": "resolved"}, "green"),
        ({"status": "resolved", "age": timedelta(days=60)}, "green"),
        ({"age": timedelta(days=15)}, "grey"),
        ({"status": "verified", "age": timedelta(days=15)}, "grey"),
        # Confirmed recently, so not stale even though it was created long ago.
        (
            {"status": "verified", "age": timedelta(days=30), "confirmed": timedelta(days=1)},
            "red",
        ),
        ({"hazard": "none"}, "green"),
        ({"hazard": "informal_shortcut", "status": "community_confirmed"}, "green"),
        ({"status": "verified"}, "red"),
        ({"status": "community_confirmed", "hazard": "car_in_bike_lane"}, "red"),
        ({"status": "unverified"}, "amber"),
        ({"status": "ai_flagged", "hazard": "other"}, "amber"),
        ({"status": "disputed"}, "amber"),
        # Contract E5: an AI failure / unsure answer is shown grey ("needs review").
        ({"status": "ai_flagged", "hazard": "other", "needs_review": True}, "grey"),
        ({"status": "resolved", "needs_review": True}, "green"),
    ],
)
def test_compute_condition_placeholder_rules(kwargs, expected):
    assert compute_condition(report(**kwargs), NOW) == expected


def test_compute_condition_always_returns_a_contract_value():
    for hazard in HazardType.values:
        for status in VerificationStatus.values:
            for age in (timedelta(0), timedelta(days=30)):
                value = compute_condition(report(hazard, status, age), NOW)
                assert value in Condition.values


def test_compute_freshness_placeholder_is_one():
    assert compute_freshness(report(), NOW) == 1.0

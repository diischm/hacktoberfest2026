"""
The ONLY place `condition` and `freshness_weight` are computed. Serializers call these.

TEMPORARY PLACEHOLDER: feat/freshness-verification replaces the internals (half-lives,
exponential decay) but keeps the two function signatures.

Placeholder rules, checked top to bottom (first match wins):

1. verification_status == resolved                        -> green
2. last confirmed (or created) more than 14 days ago      -> grey  (stale, we don't know)
3. hazard_type is not a hazard (none, informal_shortcut)  -> green
4. status verified or community_confirmed                 -> red   (confirmed hazard)
5. anything else (unverified, ai_flagged, disputed)       -> amber (unconfirmed hazard)

freshness_weight is always 1.0 for now.
"""

from datetime import datetime, timedelta

from reports.choices import NOT_A_HAZARD, Condition, VerificationStatus

STALE_AFTER = timedelta(days=14)
CONFIRMED_STATUSES = frozenset(
    {VerificationStatus.VERIFIED, VerificationStatus.COMMUNITY_CONFIRMED}
)


def compute_condition(report, now: datetime) -> str:
    if report.verification_status == VerificationStatus.RESOLVED:
        return Condition.GREEN
    last_seen = report.last_confirmed_at or report.created_at
    if now - last_seen > STALE_AFTER:
        return Condition.GREY
    if report.hazard_type in NOT_A_HAZARD:
        return Condition.GREEN
    if report.verification_status in CONFIRMED_STATUSES:
        return Condition.RED
    return Condition.AMBER


def compute_freshness(report, now: datetime) -> float:
    return 1.0

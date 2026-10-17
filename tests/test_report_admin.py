import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from reports.choices import VerificationStatus
from reports.models import Report, ReportFeedback

pytestmark = pytest.mark.django_db


def tiny_png():
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
    return SimpleUploadedFile("tiny.png", buffer.getvalue(), content_type="image/png")


@pytest.fixture
def report():
    return Report.objects.create(lat=41.9962, lng=21.4316, hazard_type="road_block")


def test_changelist_returns_200(admin_client, report):
    response = admin_client.get(reverse("admin:reports_report_changelist"))
    assert response.status_code == 200


def test_change_page_shows_photo_preview_and_feedback(admin_client, settings, report):
    report.photo = tiny_png()
    report.ai_raw_response = {"hazard_type": "road_block"}
    report.save()
    ReportFeedback.objects.create(report=report, session_key="s1", action="still_there")

    response = admin_client.get(reverse("admin:reports_report_change", args=[report.pk]))

    assert response.status_code == 200
    body = response.content.decode()
    assert f'<img src="{report.photo.url}"' in body
    assert "still_there" in body or "Still there" in body
    # The photo really went to the temporary MEDIA_ROOT, not the repo.
    assert str(settings.MEDIA_ROOT) in report.photo.path


@pytest.mark.parametrize(
    "action, expected_status",
    [
        ("mark_verified", VerificationStatus.VERIFIED),
        ("mark_resolved", VerificationStatus.RESOLVED),
        ("mark_disputed", VerificationStatus.DISPUTED),
    ],
)
def test_admin_actions_change_status(admin_client, report, action, expected_status):
    response = admin_client.post(
        reverse("admin:reports_report_changelist"),
        {"action": action, "_selected_action": [report.pk]},
    )
    assert response.status_code == 302

    report.refresh_from_db()
    assert report.verification_status == expected_status
    if action == "mark_resolved":
        assert report.resolved_at is not None
    else:
        assert report.resolved_at is None

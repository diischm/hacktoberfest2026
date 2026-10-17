import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_returns_ok_and_ai_mode(client):
    response = client.get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "ai_mode": "mock"}


@pytest.mark.django_db
def test_health_never_exposes_the_api_key(client, settings):
    settings.GEMINI_API_KEY = "fake-key-for-test"

    response = client.get(reverse("health"))

    assert "fake-key-for-test" not in response.content.decode()
    assert set(response.json()) == {"status", "ai_mode"}

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_home_page_renders(client):
    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert b"BikeAble" in response.content
    assert b'name="viewport"' in response.content

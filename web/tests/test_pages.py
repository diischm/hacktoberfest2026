import pytest
from django.urls import reverse


@pytest.mark.parametrize("name", ["web:home", "web:report", "web:routes"])
def test_page_renders(client, name):
    response = client.get(reverse(name))

    assert response.status_code == 200


def test_home_is_root_with_brand_and_viewport(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"BikeAble" in response.content
    assert b'name="viewport"' in response.content


@pytest.mark.parametrize("name", ["web:home", "web:report", "web:routes"])
def test_page_links_stylesheet(client, name):
    response = client.get(reverse(name))

    assert b"web/css/app.css" in response.content

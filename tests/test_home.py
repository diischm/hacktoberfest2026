import pytest


@pytest.mark.django_db
def test_home_page_renders(client):
    # "/" is served by the frontend's web app now; this only checks the page is there.
    response = client.get("/")

    assert response.status_code == 200
    assert b"BikeAble" in response.content
    assert b'name="viewport"' in response.content

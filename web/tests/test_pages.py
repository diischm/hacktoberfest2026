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


def test_routes_page_has_map_tabs_and_tickets(client):
    content = client.get(reverse("web:routes")).content

    assert b'id="routes-map"' in content
    assert b'id="scenario-tabs"' in content
    assert b'role="tablist"' in content
    assert b'id="route-tickets"' in content
    assert b'type="module" src="/static/web/js/routes.js"' in content
    assert b"leaflet@1.9.4/dist/leaflet.js" in content


def test_routes_js_is_safe_and_reads_colors_from_meta():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "static" / "web" / "js" / "routes.js").read_text()
    assert "innerHTML" not in js
    assert "insertAdjacentHTML" not in js
    for hex_color in ("#2E7D32", "#F9A825", "#C62828", "#757575"):
        assert hex_color.lower() not in js.lower()
    assert "TILE_LAYER.url, TILE_LAYER.options" in js

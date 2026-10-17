import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MAP_JS = (ROOT / "web" / "static" / "web" / "js" / "map.js").read_text()


@pytest.fixture
def home(client):
    return client.get("/map/")


def test_map_page_renders_with_brand_and_viewport(home):
    assert home.status_code == 200
    assert b"BikeAble" in home.content
    assert b'name="viewport"' in home.content


def test_map_page_sets_csrf_cookie(home):
    assert "csrftoken" in home.cookies


def test_leaflet_is_pinned_with_sri(home):
    html = home.content.decode()

    script = re.search(
        r'<script src="https://unpkg\.com/leaflet@1\.9\.4/dist/leaflet\.js"[^>]*>', html
    )
    style = re.search(
        r'<link rel="stylesheet" href="https://unpkg\.com/leaflet@1\.9\.4/dist/leaflet\.css"[^>]*>',
        html,
    )
    for tag in (script, style):
        assert tag is not None
        assert 'integrity="sha256-' in tag.group(0)
        assert "crossorigin" in tag.group(0)


def test_map_page_has_map_and_sheet_markup(home):
    content = home.content

    assert b'id="map"' in content
    assert b'id="detail"' in content
    assert b'id="detail-actions"' in content
    assert b'id="report-here"' in content
    assert b'type="module" src="/static/web/js/map.js"' in content


def test_fonts_load_with_display_swap(home):
    assert b"fonts.googleapis.com/css2?" in home.content
    assert b"display=swap" in home.content


def test_map_js_takes_condition_colors_from_meta():
    # Colors come from GET /api/meta/; the contract hex values must not be hardcoded in JS.
    for hex_color in ("#2E7D32", "#F9A825", "#C62828", "#757575"):
        assert hex_color.lower() not in MAP_JS.lower()


def test_map_js_never_uses_inner_html():
    assert "innerHTML" not in MAP_JS
    assert "insertAdjacentHTML" not in MAP_JS


def test_tile_layer_config_sends_referrer_and_attribution():
    # OSM tiles answer 403 without a Referer; Django's same-origin policy strips it.
    config = (ROOT / "web" / "static" / "web" / "js" / "config.js").read_text()
    tile_config = config.split("export const TILE_LAYER", 1)[1].split("};", 1)[0]

    assert 'referrerPolicy: "strict-origin-when-cross-origin"' in tile_config
    assert "attribution:" in tile_config
    assert "OpenStreetMap</a> contributors" in tile_config
    assert "TILE_LAYER.url, TILE_LAYER.options" in MAP_JS

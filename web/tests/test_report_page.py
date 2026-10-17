import re
from pathlib import Path

import pytest
from django.urls import reverse

from reports.limits import MAX_NOTE_LENGTH

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "web" / "static" / "web" / "js"
REPORT_JS = (JS / "report.js").read_text()


@pytest.fixture
def page(client):
    return client.get(reverse("web:report"))


def test_report_page_renders(page):
    assert page.status_code == 200
    assert b"Spotted something?" in page.content


def test_report_page_sets_csrf_cookie(page):
    # api.js reads this cookie and sends it as X-CSRFToken on POST /api/reports/.
    assert "csrftoken" in page.cookies


def test_photo_input_opens_the_camera(page):
    tag = re.search(r'<input type="file"[^>]*>', page.content.decode(), re.DOTALL)

    assert tag is not None
    assert 'id="photo"' in tag.group(0)
    assert 'accept="image/*"' in tag.group(0)
    assert 'capture="environment"' in tag.group(0)


def test_pick_map_and_steps_are_there(page):
    content = page.content

    assert b'id="pick-map"' in content
    assert b'id="submit-btn"' in content
    assert b'id="analyzing"' in content
    assert b'id="result"' in content
    for error_slot in (b'id="err-photo"', b'id="err-location"', b'id="err-note"'):
        assert error_slot in content


def test_note_has_maxlength_from_the_upload_limit(page):
    tag = re.search(r"<textarea[^>]*>", page.content.decode(), re.DOTALL).group(0)

    assert 'id="note"' in tag
    assert f'maxlength="{MAX_NOTE_LENGTH}"' in tag


def test_report_page_loads_leaflet_once_and_its_script(page):
    html = page.content.decode()

    assert html.count("unpkg.com/leaflet@1.9.4/dist/leaflet.js") == 1
    assert html.count("unpkg.com/leaflet@1.9.4/dist/leaflet.css") == 1
    assert 'integrity="sha256-' in html
    assert 'type="module" src="/static/web/js/report.js"' in html


def test_leaflet_tags_live_in_one_partial():
    # One copy of the pinned URLs + SRI hashes, shared by every map page.
    templates = ROOT / "web" / "templates" / "web"
    for name in ("home.html", "report.html"):
        assert "unpkg.com/leaflet" not in (templates / name).read_text()


def test_create_report_is_live():
    config = (JS / "config.js").read_text()

    assert re.search(r'createReport:\s*"live"', config)


def test_report_js_never_uses_inner_html():
    assert "innerHTML" not in REPORT_JS
    assert "insertAdjacentHTML" not in REPORT_JS
    assert "outerHTML" not in REPORT_JS


def test_report_js_reuses_shared_config():
    assert "TILE_LAYER.url, TILE_LAYER.options" in REPORT_JS
    assert "createReport(" in REPORT_JS


def test_report_js_takes_condition_colors_from_meta():
    for hex_color in ("#2E7D32", "#F9A825", "#C62828", "#757575"):
        assert hex_color.lower() not in REPORT_JS.lower()


def test_map_js_opens_a_linked_report():
    # "See it on the map" links to /?report=<id>; map.js must read that parameter.
    map_js = (JS / "map.js").read_text()

    assert 'get("report")' in map_js
    assert "/?report=" in REPORT_JS

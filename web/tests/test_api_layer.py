import json
import re
from pathlib import Path

import pytest
from django.urls import reverse

ROOT = Path(__file__).resolve().parents[2]
MOCK_DIR = ROOT / "web" / "static" / "web" / "mock"
CONTRACT = (ROOT / "docs" / "plan" / "API_CONTRACT.md").read_text()

# File names from the endpoint table in docs/plan/API_CONTRACT.md, plus error examples.
MOCK_FILES = [
    "meta.json",
    "reports.json",
    "report-101.json",
    "report-create.json",
    "report-feedback.json",
    "segments.json",
    "bike-parking.json",
    "scenarios.json",
    "routes-compare.json",
    "error-ai-rate-limited.json",
    "error-validation.json",
]


def contract_example(heading):
    """First ```json block after a heading in API_CONTRACT.md."""
    section = CONTRACT.split(heading, 1)[1]
    return json.loads(re.search(r"```json\n(.*?)```", section, re.DOTALL).group(1))


def mock(name):
    return json.loads((MOCK_DIR / name).read_text())


def test_dev_api_page_in_debug(client, settings):
    settings.DEBUG = True

    response = client.get(reverse("web:dev-api"))

    assert response.status_code == 200
    assert b"web/js/dev_api.js" in response.content
    assert "csrftoken" in response.cookies


def test_dev_api_page_hidden_without_debug(client, settings):
    settings.DEBUG = False

    assert client.get(reverse("web:dev-api")).status_code == 404


@pytest.mark.parametrize("name", MOCK_FILES)
def test_mock_file_is_valid_json(name):
    assert isinstance(mock(name), dict)


def test_meta_mock_matches_contract_keys():
    assert mock("meta.json").keys() == contract_example("### E2 Meta").keys()


def test_reports_mock_matches_contract_keys():
    data, example = mock("reports.json"), contract_example("### E3 List reports")

    assert data.keys() == example.keys()
    assert data["features"][0]["properties"].keys() == example["features"][0]["properties"].keys()


def test_mock_reports_are_marked_synthetic():
    for feature in mock("reports.json")["features"]:
        assert feature["properties"]["is_synthetic"] is True


def test_segments_mock_matches_contract_keys():
    data, example = mock("segments.json"), contract_example("### E7 Segments")

    assert data.keys() == example.keys()
    assert data["features"][0]["properties"].keys() == example["features"][0]["properties"].keys()


def test_bike_parking_mock_matches_contract_keys():
    data, example = mock("bike-parking.json"), contract_example("### E10 Bike parking")

    assert data.keys() == example.keys()
    assert data["features"][0]["properties"].keys() == example["features"][0]["properties"].keys()


@pytest.mark.parametrize("name", ["web:home", "web:report"])
def test_posting_pages_set_csrf_cookie(client, name):
    assert "csrftoken" in client.get(reverse(name)).cookies


def test_base_loads_api_modules(client):
    content = client.get("/").content

    assert b'type="module" src="/static/web/js/config.js"' in content
    assert b'type="module" src="/static/web/js/api.js"' in content

import pytest
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from config.exceptions import api_exception_handler
from reports.views import MetaView

pytestmark = pytest.mark.django_db


def assert_error_shape(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert {"code", "message", "fields"} <= set(body["error"])
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert isinstance(body["error"]["fields"], dict)
    return body["error"]


def test_unknown_report_is_contract_404(client):
    error = assert_error_shape(client.get("/api/reports/999999/"), 404, "not_found")
    assert error["fields"] == {}


def test_non_numeric_report_id_is_contract_404(client):
    assert_error_shape(client.get("/api/reports/abc/"), 404, "not_found")


def test_wrong_method_is_contract_405(client):
    assert_error_shape(client.delete("/api/meta/"), 405, "method_not_allowed")


def test_validation_error_lists_fields():
    response = api_exception_handler(ValidationError({"lat": ["Bad lat."]}), {})
    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert response.data["error"]["fields"] == {"lat": ["Bad lat."]}


def test_unexpected_error_is_500_without_internals(monkeypatch, caplog):
    def boom(self, request):
        raise RuntimeError("secret-internal-detail /home/dimi/db.sqlite3")

    monkeypatch.setattr(MetaView, "get", boom)
    response = MetaView.as_view()(APIRequestFactory().get("/api/meta/"))
    response.render()

    assert response.status_code == 500
    assert response.data == {
        "error": {
            "code": "server_error",
            "message": "Something went wrong on our side.",
            "fields": {},
        }
    }
    body = response.content.decode()
    assert "secret-internal-detail" not in body
    assert "Traceback" not in body
    # The traceback still reaches the server log for debugging.
    assert "secret-internal-detail" in caplog.text

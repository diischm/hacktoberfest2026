import pytest


def assert_contract_404(response):
    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not found.", "fields": {}}
    }


@pytest.mark.parametrize("path", ["/api/does-not-exist/", "/api/", "/api/a/b/c/"])
def test_unknown_api_path_is_contract_404(client, path):
    assert_contract_404(client.get(path))


def test_unknown_api_path_is_404_for_any_method(client):
    # Not 405 and not a CSRF error: the path simply doesn't exist.
    assert_contract_404(client.post("/api/does-not-exist/", {}, content_type="application/json"))
    assert_contract_404(client.delete("/api/does-not-exist/"))


def test_unknown_api_path_without_slash_redirects_then_404s(client):
    response = client.get("/api/does-not-exist", follow=True)
    assert response.redirect_chain == [("/api/does-not-exist/", 301)]
    assert_contract_404(response)


@pytest.mark.django_db
def test_known_api_path_without_slash_still_redirects(client):
    response = client.get("/api/reports")
    assert response.status_code == 301
    assert response["Location"] == "/api/reports/"


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/api/health/", "/api/meta/", "/api/reports/", "/"])
def test_known_paths_still_work(client, path):
    assert client.get(path).status_code == 200


def test_unknown_non_api_path_keeps_django_404(client):
    response = client.get("/does-not-exist/")
    assert response.status_code == 404
    assert not response["Content-Type"].startswith("application/json")
    assert b'"error"' not in response.content

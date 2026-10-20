import logging

import pytest
from django.test import Client

CATALOG = "/api/v1/catalog"
# Matches `config.settings_test`.
TOKEN = "t" * 40


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client():
    """A client that enforces CSRF like a real request, so the views must stay `csrf_exempt`."""
    return Client(enforce_csrf_checks=True)


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no-header"),
        pytest.param(bearer("wrong-token-" + "x" * 30), id="wrong-token"),
        pytest.param(bearer(TOKEN[:-1] + "u"), id="last-character-differs"),
        pytest.param(bearer(TOKEN[:-1]), id="prefix"),
        pytest.param({"Authorization": TOKEN}, id="no-scheme"),
        pytest.param({"Authorization": f"Basic {TOKEN}"}, id="other-scheme"),
    ],
)
def test_rejects_a_missing_or_wrong_token(client, headers, caplog):
    with caplog.at_level(logging.WARNING, logger="cb.storefront"):
        response = client.get(CATALOG, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}
    assert response["Cache-Control"] == "no-store"
    assert "api.unauthorized" in caplog.text
    assert "t" * 20 not in caplog.text
    assert "wrong-token" not in caplog.text


def test_accepts_the_right_token(client):
    response = client.get(CATALOG, headers=bearer(TOKEN))

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response["Content-Type"] == "application/json"


def test_accepts_a_lowercase_scheme(client):
    assert client.get(CATALOG, headers={"Authorization": f"bearer {TOKEN}"}).status_code == 200


@pytest.mark.parametrize("configured", ["", "s" * 31])
def test_fails_closed_without_a_configured_token(client, settings, configured):
    settings.INTERNAL_API_TOKEN = configured

    response = client.get(CATALOG, headers=bearer(configured))

    assert response.status_code == 503
    assert response.json() == {"error": "unavailable"}
    assert response["Cache-Control"] == "no-store"


def test_post_is_not_allowed_and_not_cached(client):
    response = client.post(CATALOG, headers=bearer(TOKEN))

    assert response.status_code == 405
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize("path", ["/api/v1/catalog", "/api/v1/availability"])
def test_every_endpoint_is_guarded(client, path):
    response = client.get(path)

    assert response.status_code == 401
    assert response["Cache-Control"] == "no-store"

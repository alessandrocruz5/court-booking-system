from django.conf import settings
from django.http import HttpResponse
from django.test import Client, override_settings
from django.urls import path


def _boom(request):
    raise RuntimeError("boom")


def _read_body(request):
    return HttpResponse(request.body)


# A URL config for the errors no real view raises on purpose: a 500, and `RequestDataTooBig`.
urlpatterns = [
    path("api/v1/boom", _boom),
    path("webhooks/body", _read_body),
]


def test_middleware_is_outermost():
    assert settings.MIDDLEWARE[0] == "core.middleware.NoStoreMiddleware"


def test_unmatched_api_route_is_not_cached(client):
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response["Cache-Control"] == "no-store"


def test_api_root_without_trailing_slash_is_not_cached(client):
    response = client.get("/api/v1")

    assert response.status_code == 404
    assert response["Cache-Control"] == "no-store"


def test_unmatched_webhook_route_is_not_cached(client):
    response = client.get("/webhooks/does-not-exist")

    assert response.status_code == 404
    assert response["Cache-Control"] == "no-store"


def test_disallowed_host_on_webhook_is_not_cached(client):
    response = client.post("/webhooks/paymongo", HTTP_HOST="evil.example")

    assert response.status_code == 400
    assert response["Cache-Control"] == "no-store"


@override_settings(ROOT_URLCONF=__name__)
def test_server_error_is_not_cached():
    response = Client(raise_request_exception=False).get("/api/v1/boom")

    assert response.status_code == 500
    assert response["Cache-Control"] == "no-store"


@override_settings(ROOT_URLCONF=__name__, DATA_UPLOAD_MAX_MEMORY_SIZE=10)
def test_request_data_too_big_is_not_cached(client):
    response = client.post("/webhooks/body", data="x" * 100, content_type="application/json")

    assert response.status_code == 400
    assert response["Cache-Control"] == "no-store"


def test_api_view_sends_no_store(client):
    response = client.get("/api/v1/catalog")

    assert response.status_code in (401, 503)
    assert response["Cache-Control"] == "no-store"


def test_paths_outside_the_prefixes_are_untouched(client):
    response = client.get("/")

    assert response.status_code in (301, 302)
    assert "no-store" not in response.get("Cache-Control", "")

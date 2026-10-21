def test_unmatched_api_route_is_not_cached(client):
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response["Cache-Control"] == "no-store"


def test_api_root_without_trailing_slash_is_not_cached(client):
    response = client.get("/api/v1")

    assert response["Cache-Control"] == "no-store"


def test_unmatched_webhook_route_is_not_cached(client):
    response = client.get("/webhooks/does-not-exist")

    assert response.status_code == 404
    assert response["Cache-Control"] == "no-store"


def test_disallowed_host_on_webhook_is_not_cached(client):
    response = client.post("/webhooks/paymongo", HTTP_HOST="evil.example")

    assert response.status_code == 400
    assert response["Cache-Control"] == "no-store"


def test_api_view_still_sends_no_store(client):
    response = client.get("/api/v1/catalog")

    assert response.status_code in (401, 503)
    assert response["Cache-Control"] == "no-store"


def test_paths_outside_the_prefixes_are_untouched(client):
    response = client.get("/")

    assert response.status_code in (301, 302)
    assert "no-store" not in response.get("Cache-Control", "")

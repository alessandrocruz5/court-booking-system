import pytest


@pytest.mark.django_db
def test_healthz_is_ok_uncached_and_queries_nothing(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["Cache-Control"] == "no-store"


def test_healthz_rejects_post(client):
    response = client.post("/health")

    assert response.status_code == 405

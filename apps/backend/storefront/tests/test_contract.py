"""The storefront API against `docs/api/fixtures/*.json`, which the web app's tests also read.

The catalog must equal its fixture exactly; the other responses must have the fixture's shape.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from django.conf import settings
from django.utils import timezone

from bookings import holds, rules
from bookings.holds import Customer
from bookings.models import Court
from bookings.rules import Status
from payments import confirm
from payments.confirm import CheckResult
from storefront import views
from storefront.tests.test_bookings_api import booking_body, use_fake_paymongo

FIXTURES = Path(settings.BASE_DIR).parent.parent / "docs/api/fixtures"
# Matches `config.settings_test`.
AUTH = {"Authorization": "Bearer " + "t" * 40}


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


def json_type(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise TypeError(type(value).__name__)


def assert_same_shape(actual, expected, path: str = "$") -> None:
    """Same keys and JSON types, recursively. Each element of a list is checked against the
    fixture's first element."""
    assert json_type(actual) == json_type(expected), f"{path}: {json_type(actual)}"
    if isinstance(expected, dict):
        assert sorted(actual) == sorted(expected), f"{path}: keys {sorted(actual)}"
        for key, value in expected.items():
            assert_same_shape(actual[key], value, f"{path}.{key}")
    elif isinstance(expected, list) and expected:
        for index, item in enumerate(actual):
            assert_same_shape(item, expected[0], f"{path}[{index}]")


def test_shape_check_catches_drift():
    expected = {"a": 1, "b": [{"c": True}]}
    assert_same_shape({"a": 2, "b": [{"c": False}, {"c": True}]}, expected)
    for drifted in (
        {"a": "1", "b": []},
        {"a": 1},
        {"a": 1, "b": [], "extra": None},
        {"a": True, "b": []},
        {"a": 1, "b": [{"c": 1}]},
    ):
        with pytest.raises(AssertionError):
            assert_same_shape(drifted, expected)


def test_catalog_equals_its_fixture(client):
    response = client.get("/api/v1/catalog", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == fixture("catalog.json")


@pytest.mark.django_db
def test_availability_has_the_fixture_shape(client):
    day = rules.local_today(timezone.now()) + timedelta(days=1)
    response = client.get(
        "/api/v1/availability",
        {"date": day.isoformat(), "sport": "basketball", "coverage": "half", "hours": "2"},
        headers=AUTH,
    )

    assert response.status_code == 200
    body = response.json()
    assert all(court["starts"] for court in body["courts"])
    assert_same_shape(body, fixture("availability.json"))


def test_error_has_the_fixture_shape(client):
    response = client.get("/api/v1/availability", {"sport": "tennis"}, headers=AUTH)

    assert response.status_code == 400
    assert_same_shape(response.json(), fixture("error.json"))
    assert response.json() == fixture("error.json")


def post(client, path: str, body: dict):
    return client.post(path, json.dumps(body), content_type="application/json", headers=AUTH)


def tennis_hold(session_id: str = "cs_test123"):
    booking = holds.create_hold(
        court=Court.objects.get(code="tn-2"),
        sport="tennis",
        coverage="full",
        day=rules.local_today(timezone.now()) + timedelta(days=1),
        start_hour=18,
        hours=2,
        customer=Customer(name="Ana Reyes", email="ana.reyes@example.com", mobile="+639000000789"),
    )
    booking.checkout_session_id = session_id
    booking.save(update_fields=["checkout_session_id"])
    return booking


@pytest.mark.django_db
def test_booking_created_has_the_fixture_shape(client, monkeypatch):
    use_fake_paymongo(monkeypatch)

    response = post(client, "/api/v1/bookings", booking_body())

    assert response.status_code == 201
    assert_same_shape(response.json(), fixture("booking-created.json"))


@pytest.mark.django_db
def test_checkout_status_has_the_fixture_shape(client, monkeypatch):
    booking = tennis_hold()
    booking.status = Status.CONFIRMED
    booking.hold_expires_at = None
    booking.payment_method = "gcash"
    booking.paid_at = datetime(2026, 10, 30, 6, 7, 12, tzinfo=UTC)
    booking.save()
    monkeypatch.setattr(
        views, "check_checkout", MagicMock(return_value=CheckResult("confirmed", booking))
    )

    response = post(client, "/api/v1/checkout/confirm", {"checkout_session_id": "cs_test123"})

    assert response.status_code == 200
    assert_same_shape(response.json(), fixture("checkout-status.json"))


@pytest.mark.django_db
def test_checkout_release_has_the_fixture_shape(client, monkeypatch):
    monkeypatch.setattr(confirm, "get_client", MagicMock(name="get_client"))
    tennis_hold()

    response = post(client, "/api/v1/checkout/release", {"checkout_session_id": "cs_test123"})

    assert response.status_code == 200
    assert response.json() == fixture("checkout-release.json")


@pytest.mark.django_db
def test_booking_lookup_has_the_fixture_shape(client):
    booking = tennis_hold()

    response = post(
        client,
        "/api/v1/bookings/lookup",
        {
            "reference": booking.reference,
            "email": "ana.reyes@example.com",
            "client_ip": "192.0.2.1",
        },
    )

    assert response.status_code == 200
    assert_same_shape(response.json(), fixture("booking-lookup.json"))

"""`POST /api/v1/checkout/confirm`, `/checkout/release` and `/bookings/lookup`."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from bookings import holds, rules
from bookings.holds import Customer
from bookings.models import Booking, Court, SlotLock
from bookings.rules import Status
from core import ratelimit
from payments import confirm
from payments.confirm import CheckResult
from storefront import views
from storefront.payloads import booking_summary

# Matches `config.settings_test`.
AUTH = {"Authorization": "Bearer " + "t" * 40}
SESSION_ID = "cs_test123"
CUSTOMER = Customer(name="Jose Rizal", email="jose.rizal@example.com", mobile="+639000000456")
PII = (CUSTOMER.name, CUSTOMER.email, CUSTOMER.mobile)
SUMMARY_KEYS = {
    "reference",
    "status",
    "court",
    "sport",
    "coverage",
    "half",
    "date",
    "start_hour",
    "hours",
    "price_centavos",
    "hold_expires_at",
    "paid_at",
    "payment_method",
}


def post(client, path, body, **headers):
    return client.post(
        path, json.dumps(body), content_type="application/json", headers={**AUTH, **headers}
    )


def make_hold(code: str = "bb-1", *, coverage: str = "half", session_id: str | None = SESSION_ID):
    booking = holds.create_hold(
        court=Court.objects.get(code=code),
        sport="basketball" if code.startswith("bb") else "tennis",
        coverage=coverage,
        day=rules.local_today(timezone.now()) + timedelta(days=1),
        start_hour=15,
        hours=2,
        customer=CUSTOMER,
    )
    if session_id is not None:
        booking.checkout_session_id = session_id
        booking.save(update_fields=["checkout_session_id"])
    return booking


def mark_paid(booking: Booking) -> Booking:
    booking.status = Status.CONFIRMED
    booking.hold_expires_at = None
    booking.payment_id = "pay_test1"
    booking.payment_method = "gcash"
    booking.paid_at = datetime(2026, 10, 30, 6, 7, tzinfo=UTC)
    booking.save()
    return booking


def assert_no_pii(text: str) -> None:
    for value in PII:
        assert value not in text


def mock_paymongo(monkeypatch) -> MagicMock:
    """Replace `payments.confirm.get_client`, so nothing reaches PayMongo."""
    factory = MagicMock(name="get_client")
    monkeypatch.setattr(confirm, "get_client", factory)
    return factory


# confirm


@pytest.mark.django_db
def test_confirm_returns_the_status_and_the_booking(client, monkeypatch):
    booking = mark_paid(make_hold())
    check = MagicMock(return_value=CheckResult("confirmed", booking))
    monkeypatch.setattr(views, "check_checkout", check)

    response = post(client, "/api/v1/checkout/confirm", {"checkout_session_id": SESSION_ID})

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    check.assert_called_once_with(SESSION_ID)
    body = response.json()
    assert body == {"status": "confirmed", "booking": booking_summary(booking)}
    assert set(body["booking"]) == SUMMARY_KEYS
    local_start = booking.starts_at.astimezone(rules.TIME_ZONE)
    assert body["booking"]["court"] == {"code": "bb-1", "name": "Basketball Court 1"}
    assert (body["booking"]["coverage"], body["booking"]["half"]) == ("half", "A")
    assert body["booking"]["date"] == local_start.date().isoformat()
    assert body["booking"]["start_hour"] == 15
    assert body["booking"]["paid_at"] == "2026-10-30T14:07:00+08:00"
    assert body["booking"]["payment_method"] == "gcash"
    assert body["booking"]["hold_expires_at"] is None
    assert_no_pii(response.content.decode())


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("result", "expected"),
    [
        pytest.param(CheckResult("not_found"), "not_found", id="not_found"),
        pytest.param(CheckResult("unavailable"), "unavailable", id="unavailable"),
    ],
)
def test_confirm_without_a_booking_answers_null(client, monkeypatch, result, expected):
    monkeypatch.setattr(views, "check_checkout", MagicMock(return_value=result))

    response = post(client, "/api/v1/checkout/confirm", {"checkout_session_id": SESSION_ID})

    assert response.status_code == 200
    assert response.json() == {"status": expected, "booking": None}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("final", "stored"),
    [
        pytest.param(Status.EXPIRED, Status.EXPIRED, id="expired"),
        pytest.param(Status.CANCELLED, Status.CANCELLED, id="cancelled"),
        pytest.param(None, Status.PENDING, id="lapsed-not-swept"),
    ],
)
def test_confirm_reports_a_lapsed_or_cancelled_hold(client, monkeypatch, final, stored):
    """`check_checkout` says `pending` for a released hold with no paid payment; the page must
    not keep saying "still processing". Holds expire lazily, so a lapsed hold may still be
    stored as `pending`."""
    booking = make_hold()
    if final is None:
        Booking.objects.filter(pk=booking.pk).update(hold_expires_at=timezone.now())
        booking.refresh_from_db()
    else:
        holds.release(booking, status=final)
    monkeypatch.setattr(
        views, "check_checkout", MagicMock(return_value=CheckResult("pending", booking))
    )

    response = post(client, "/api/v1/checkout/confirm", {"checkout_session_id": SESSION_ID})

    assert response.json()["status"] == (final or Status.EXPIRED)
    assert response.json()["booking"]["status"] == stored


@pytest.mark.django_db
def test_confirm_keeps_pending_for_a_live_hold(client, monkeypatch):
    booking = make_hold()
    monkeypatch.setattr(
        views, "check_checkout", MagicMock(return_value=CheckResult("pending", booking))
    )

    response = post(client, "/api/v1/checkout/confirm", {"checkout_session_id": SESSION_ID})

    assert booking.hold_expires_at > timezone.now()
    assert response.json()["status"] == "pending"


@pytest.mark.django_db
@pytest.mark.parametrize("body", [{}, {"checkout_session_id": 7}, {"checkout_session_id": ""}])
def test_confirm_needs_a_session_id(client, monkeypatch, body):
    check = MagicMock()
    monkeypatch.setattr(views, "check_checkout", check)

    response = post(client, "/api/v1/checkout/confirm", body)

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request", "fields": ["checkout_session_id"]}
    check.assert_not_called()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_confirm_runs_check_checkout_outside_a_transaction(client, monkeypatch):
    """The real `check_checkout` refuses to run inside `atomic()`; a paid booking answers without
    asking PayMongo."""
    factory = mock_paymongo(monkeypatch)
    booking = mark_paid(make_hold("tn-1", coverage="full"))

    response = post(client, "/api/v1/checkout/confirm", {"checkout_session_id": SESSION_ID})

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert response.json()["booking"]["reference"] == booking.reference
    factory.assert_not_called()


# release


@pytest.mark.django_db
def test_release_frees_a_pending_hold(client, monkeypatch):
    mock_paymongo(monkeypatch)
    booking = make_hold()

    response = post(client, "/api/v1/checkout/release", {"checkout_session_id": SESSION_ID})

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response.json() == {"status": "released"}
    booking.refresh_from_db()
    assert booking.status == Status.CANCELLED
    assert not SlotLock.objects.filter(booking=booking).exists()


@pytest.mark.django_db
def test_release_never_cancels_a_paid_booking(client, monkeypatch):
    mock_paymongo(monkeypatch)
    mark_paid(make_hold())

    response = post(client, "/api/v1/checkout/release", {"checkout_session_id": SESSION_ID})

    assert response.json() == {"status": "already_paid"}


@pytest.mark.django_db
def test_release_of_an_unknown_session(client, monkeypatch):
    mock_paymongo(monkeypatch)

    response = post(client, "/api/v1/checkout/release", {"checkout_session_id": "cs_unknown"})

    assert response.json() == {"status": "not_found"}


# lookup


def lookup(client, *, reference, email=CUSTOMER.email, client_ip="198.51.100.7"):
    return post(
        client,
        "/api/v1/bookings/lookup",
        {"reference": reference, "email": email, "client_ip": client_ip},
    )


@pytest.fixture
def pinned_clock(monkeypatch):
    """Freeze the clock `core.ratelimit` reads, so a run can't straddle a window boundary."""
    frozen = timezone.now()
    monkeypatch.setattr(ratelimit, "timezone", SimpleNamespace(now=lambda: frozen))


@pytest.mark.django_db
def test_lookup_finds_a_booking_by_reference_and_email(client, pinned_clock):
    booking = make_hold()

    response = lookup(client, reference=booking.reference)

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response.json() == {"booking": booking_summary(booking)}
    assert response.json()["booking"]["status"] == "pending"
    assert_no_pii(response.content.decode())


@pytest.mark.django_db
def test_lookup_trims_and_ignores_case(client, pinned_clock):
    booking = make_hold()

    response = lookup(
        client, reference=f"  {booking.reference.lower()} ", email=f" {CUSTOMER.email.upper()} "
    )

    assert response.status_code == 200
    assert response.json()["booking"]["reference"] == booking.reference


@pytest.mark.django_db
def test_wrong_email_and_wrong_reference_look_the_same(client, pinned_clock):
    booking = make_hold()

    wrong_email = lookup(client, reference=booking.reference, email="someone.else@example.com")
    wrong_reference = lookup(client, reference="KC-000000")

    assert wrong_email.status_code == wrong_reference.status_code == 404
    assert wrong_email.content == wrong_reference.content
    assert wrong_email.json() == {"error": "not_found"}
    assert dict(wrong_email.headers) == dict(wrong_reference.headers)


@pytest.mark.django_db
def test_an_anonymized_booking_is_not_found(client, pinned_clock):
    booking = make_hold()
    Booking.objects.filter(pk=booking.pk).update(anonymized_at=timezone.now())

    response = lookup(client, reference=booking.reference)

    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}


@pytest.mark.django_db
def test_eleventh_lookup_from_one_ip_is_rate_limited(client, pinned_clock):
    booking = make_hold()
    for _ in range(10):
        assert lookup(client, reference=booking.reference).status_code == 200

    response = lookup(client, reference=booking.reference)

    assert response.status_code == 429
    assert response.json() == {"error": "rate_limited"}
    # Another IP has its own window.
    assert lookup(client, reference=booking.reference, client_ip="198.51.100.8").status_code == 200


@pytest.mark.django_db
def test_lookups_from_one_ipv6_64_share_a_window(client, pinned_clock):
    booking = make_hold()
    for n in range(10):
        response = lookup(client, reference=booking.reference, client_ip=f"2001:db8:7:8::{n + 1:x}")
        assert response.status_code == 200

    response = lookup(client, reference=booking.reference, client_ip="2001:db8:7:8:abcd::1")

    assert response.status_code == 429
    assert response.json() == {"error": "rate_limited"}


@pytest.mark.django_db
def test_lookup_names_invalid_fields(client):
    response = post(
        client,
        "/api/v1/bookings/lookup",
        {"reference": " ", "email": "a\x00@example.com", "client_ip": "nope"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_request",
        "fields": ["reference", "email", "client_ip"],
    }


# auth


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/bookings",
        "/api/v1/bookings/lookup",
        "/api/v1/checkout/confirm",
        "/api/v1/checkout/release",
    ],
)
def test_every_write_endpoint_needs_the_token(client, path):
    response = client.post(path, "{}", content_type="application/json")

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}
    assert response["Cache-Control"] == "no-store"

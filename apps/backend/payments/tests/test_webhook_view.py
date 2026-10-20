import hashlib
import hmac
import json
import logging
import time
from datetime import date, datetime

import pytest

from bookings import holds, rules
from bookings.holds import Customer
from bookings.models import Booking, Court
from bookings.rules import Status
from payments import views
from payments.webhook import CHECKOUT_SESSION_PAID, SIGNATURE_TOLERANCE_SECONDS

URL = "/webhooks/paymongo"
SECRET = "whsk_testsecret"
SESSION_ID = "cs_test1"
NOW = datetime(2026, 11, 2, 10, tzinfo=rules.TIME_ZONE)
CUSTOMER = Customer(
    name="Juan Dela Cruz", email="juan.delacruz@example.com", mobile="+639000000001"
)


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setenv("PAYMONGO_WEBHOOK_SECRET", SECRET)


def make_booking() -> Booking:
    """A pending hold with its locks, whose hold never lapses at the real time the view runs."""
    booking = holds.create_hold(
        court=Court.objects.get(code="tn-1"),
        sport="tennis",
        coverage="full",
        day=date(2026, 11, 3),
        start_hour=12,
        hours=1,
        customer=CUSTOMER,
        now=NOW,
    )
    Booking.objects.filter(pk=booking.pk).update(
        checkout_session_id=SESSION_ID, hold_expires_at=datetime(2099, 1, 1, tzinfo=rules.TIME_ZONE)
    )
    booking.refresh_from_db()
    return booking


def session_resource(booking_id: str, amount: int) -> dict:
    return {
        "id": SESSION_ID,
        "type": "checkout_session",
        "attributes": {
            "checkout_url": f"https://checkout.paymongo.com/{SESSION_ID}",
            "status": "active",
            "livemode": False,
            "metadata": {"booking_id": booking_id},
            "payments": [
                {
                    "id": "pay_test1",
                    "type": "payment",
                    "attributes": {
                        "amount": amount,
                        "currency": "PHP",
                        "fee": 1_250,
                        "net_amount": amount - 1_250,
                        "status": "paid",
                        "livemode": False,
                        "paid_at": 1_793_600_000,
                        "source": {"id": "src_x", "type": "gcash"},
                    },
                }
            ],
        },
    }


def event_body(data: object, *, type_: str = CHECKOUT_SESSION_PAID, livemode=False) -> bytes:
    return json.dumps(
        {
            "data": {
                "id": "evt_test1",
                "type": "event",
                "attributes": {"type": type_, "livemode": livemode, "data": data},
            }
        }
    ).encode()


def signature(raw: bytes, *, t: int | None = None, secret: str = SECRET) -> str:
    t = int(time.time()) if t is None else t
    te = hmac.new(secret.encode(), f"{t}.".encode() + raw, hashlib.sha256).hexdigest()
    return f"t={t},te={te},li="


def post(client, raw: bytes, header: str | None = "sign"):
    headers = {}
    if header == "sign":
        headers["Paymongo-Signature"] = signature(raw)
    elif header is not None:
        headers["Paymongo-Signature"] = header
    response = client.post(URL, data=raw, content_type="application/json", headers=headers)
    assert response["Cache-Control"] == "no-store"
    return response


@pytest.mark.django_db
def test_no_signature_is_401_before_any_query(client, django_assert_num_queries, caplog):
    raw = event_body({})
    with django_assert_num_queries(0):
        response = post(client, raw, header=None)

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_signature"}
    assert "webhook.unauthorized reason=missing" in caplog.text


@pytest.mark.django_db
def test_bad_signature_is_401(client, django_assert_num_queries):
    raw = event_body({})
    with django_assert_num_queries(0):
        response = post(client, raw, header=signature(raw, secret="whsk_other"))
    assert response.status_code == 401
    assert response.json() == {"error": "invalid_signature"}


@pytest.mark.django_db
def test_tampered_body_is_401(client):
    raw = event_body({})
    response = post(client, raw + b" ", header=signature(raw))
    assert response.status_code == 401


@pytest.mark.django_db
def test_stale_signature_is_401(client, caplog):
    raw = event_body({})
    stale = int(time.time()) - SIGNATURE_TOLERANCE_SECONDS - 60
    response = post(client, raw, header=signature(raw, t=stale))
    assert response.status_code == 401
    assert "webhook.unauthorized reason=stale" in caplog.text


@pytest.mark.django_db
def test_livemode_event_is_400(client):
    response = post(client, event_body({}, livemode=True))
    assert response.status_code == 400
    assert response.json() == {"error": "livemode"}


@pytest.mark.django_db
@pytest.mark.parametrize("raw", [b"not json", b"[]", b'{"data":{"id":"evt_1"}}'])
def test_unreadable_event_is_400(client, raw):
    response = post(client, raw)
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_event"}


@pytest.mark.django_db
def test_bad_checkout_session_is_400(client):
    response = post(client, event_body({"id": "not-a-session"}))
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_event"}


@pytest.mark.django_db
def test_other_event_type_is_ignored(client):
    response = post(client, event_body({}, type_="payment.failed"))
    assert response.status_code == 200
    assert response.json() == {"outcome": "ignored"}


@pytest.mark.django_db
def test_paid_event_confirms_the_booking(client, caplog):
    caplog.set_level(logging.INFO, logger="cb.payments")
    booking = make_booking()
    raw = event_body(session_resource(str(booking.id), booking.price_centavos))

    response = post(client, raw)

    assert response.status_code == 200
    assert response.json() == {"outcome": "confirmed"}
    booking.refresh_from_db()
    assert booking.status == Status.CONFIRMED
    assert booking.payment_id == "pay_test1"
    for value in (CUSTOMER.name, CUSTOMER.email, CUSTOMER.mobile):
        assert value not in caplog.text


@pytest.mark.django_db
def test_same_event_twice_is_200_both_times(client):
    booking = make_booking()
    raw = event_body(session_resource(str(booking.id), booking.price_centavos))

    first = post(client, raw)
    booking.refresh_from_db()
    first_write = booking.updated_at
    second = post(client, raw)

    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json() == second.json() == {"outcome": "confirmed"}
    booking.refresh_from_db()
    assert booking.updated_at == first_write


@pytest.mark.django_db
def test_rejected_payment_is_200_so_paymongo_stops_retrying(client):
    booking = make_booking()
    raw = event_body(session_resource(str(booking.id), booking.price_centavos + 1))

    response = post(client, raw)

    assert response.status_code == 200
    assert response.json() == {"outcome": "rejected"}
    booking.refresh_from_db()
    assert booking.status == Status.PENDING


@pytest.mark.django_db
def test_unexpected_error_is_500_so_paymongo_retries(client, monkeypatch, caplog):
    def boom(session):
        raise RuntimeError("juan.delacruz@example.com")

    monkeypatch.setattr(views, "confirm_payment", boom)
    response = post(client, event_body(session_resource("x", 100)))

    assert response.status_code == 500
    assert response.json() == {"error": "unavailable"}
    assert "webhook.confirm_failed event_id=evt_test1 session=cs_test1 error=RuntimeError" in (
        caplog.text
    )
    assert "juan" not in caplog.text


@pytest.mark.django_db
def test_missing_secret_is_500(client, monkeypatch, django_assert_num_queries, caplog):
    monkeypatch.delenv("PAYMONGO_WEBHOOK_SECRET")
    raw = event_body({})
    with django_assert_num_queries(0):
        response = post(client, raw)

    assert response.status_code == 500
    assert response.json() == {"error": "unavailable"}
    assert "webhook.env_failed error=PaymentsConfigError key=PAYMONGO_WEBHOOK_SECRET" in (
        caplog.text
    )


def test_get_is_405(client):
    response = client.get(URL)
    assert response.status_code == 405
    assert response["Cache-Control"] == "no-store"

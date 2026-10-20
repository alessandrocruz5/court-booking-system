"""`POST /api/v1/bookings`: validation, rate limits, the hold, then the PayMongo checkout session.

PayMongo is replaced by `FakePayMongo` (patched over `storefront.views.get_client`), which records
every argument it receives so the tests can prove no customer data reaches it.
"""

import json
import logging
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, connection
from django.utils import timezone

from bookings import pricing, rules
from bookings.models import Booking, Court, SlotLock
from bookings.rules import Status
from core import ratelimit
from payments.paymongo import CheckoutSession, PayMongoError
from storefront import views

URL = "/api/v1/bookings"
# Matches `config.settings_test`.
AUTH = {"Authorization": "Bearer " + "t" * 40}
SESSION_ID = "cs_test123"
CHECKOUT_URL = f"https://checkout.paymongo.com/{SESSION_ID}"
NAME = "Maria Clara Santos"
EMAIL = "maria.santos@example.com"
MOBILE = "+639000000123"


class FakePayMongo:
    """Stands in for `get_client()`: a context manager whose `create_checkout_session` records its
    keyword arguments and returns a session, or raises `error`. The first session is `cs_test123`;
    later ones get a numeric suffix, since the column is unique."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict] = []

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> None:
        return None

    def create_checkout_session(self, **kwargs) -> CheckoutSession:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        session_id = SESSION_ID if len(self.calls) == 1 else f"{SESSION_ID}{len(self.calls)}"
        return CheckoutSession(
            id=session_id,
            checkout_url=f"https://checkout.paymongo.com/{session_id}",
            status="active",
            livemode=False,
            metadata={"booking_id": kwargs["booking_id"]},
            payments=(),
        )


def use_fake_paymongo(monkeypatch, error: Exception | None = None) -> FakePayMongo:
    fake = FakePayMongo(error)
    monkeypatch.setattr(views, "get_client", fake)
    return fake


def pin_ratelimit_clock(monkeypatch) -> None:
    """Freeze the clock `core.ratelimit` reads, so a run can't straddle a window boundary."""
    frozen = timezone.now()
    monkeypatch.setattr(ratelimit, "timezone", SimpleNamespace(now=lambda: frozen))


def tomorrow():
    return rules.local_today(timezone.now()) + timedelta(days=1)


def booking_body(**changes) -> dict:
    body = {
        "court": "tn-1",
        "sport": "tennis",
        "coverage": "full",
        "date": tomorrow().isoformat(),
        "start_hour": 10,
        "hours": 2,
        "customer": {"name": NAME, "email": EMAIL, "mobile": MOBILE},
        "consent": True,
        "client_ip": "203.0.113.10",
    }
    body.update(changes)
    return body


def customer(**changes) -> dict:
    return {"name": NAME, "email": EMAIL, "mobile": MOBILE, **changes}


def post(client, body, **headers):
    data = body if isinstance(body, str | bytes) else json.dumps(body)
    return client.post(URL, data, content_type="application/json", headers={**AUTH, **headers})


@pytest.fixture
def fake(monkeypatch) -> FakePayMongo:
    return use_fake_paymongo(monkeypatch)


@pytest.mark.django_db
def test_creates_a_hold_and_a_checkout_session(client, fake):
    before = timezone.now()
    response = post(client, booking_body())

    assert response.status_code == 201
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    booking = Booking.objects.get(reference=body["reference"])
    assert booking.status == Status.PENDING
    assert booking.checkout_session_id == SESSION_ID
    assert booking.price_centavos == pricing.quote("tennis", "full", tomorrow(), 10, 2)
    assert booking.consent_at is not None and booking.consent_at >= before
    assert booking.customer_email == EMAIL
    assert body == {
        "reference": booking.reference,
        "checkout_url": CHECKOUT_URL,
        "checkout_session_id": SESSION_ID,
        "hold_expires_at": booking.hold_expires_at.astimezone(rules.TIME_ZONE).isoformat(),
        "price_centavos": booking.price_centavos,
    }
    assert datetime.fromisoformat(body["hold_expires_at"]) == booking.hold_expires_at


@pytest.mark.django_db
def test_normalizes_the_customer_fields(client, fake):
    response = post(
        client,
        booking_body(
            customer=customer(
                name="  Maria  ", email=" Maria.Santos@Example.COM ", mobile="09000000123"
            )
        ),
    )

    assert response.status_code == 201
    booking = Booking.objects.get(reference=response.json()["reference"])
    assert booking.customer_name == "Maria"
    assert booking.customer_email == EMAIL
    assert booking.customer_mobile == MOBILE


@pytest.mark.django_db
def test_sends_paymongo_the_booking_id_and_no_customer_data(client, fake):
    response = post(client, booking_body())

    assert response.status_code == 201
    booking = Booking.objects.get(reference=response.json()["reference"])
    (call,) = fake.calls
    assert call["booking_id"] == str(booking.id)
    assert call["amount_centavos"] == booking.price_centavos
    assert call["description"] == f"Kalaro Courts booking {booking.reference} (test mode)"
    assert call["success_url"] == "http://localhost:3000/book/success"
    assert call["cancel_url"] == "http://localhost:3000/book/cancelled"
    assert call["line_item_name"].startswith("Tennis Court 1 · Tennis · ")
    assert call["line_item_name"].endswith(", 10 AM–12 PM")
    for value in call.values():
        if isinstance(value, str):
            for pii in (EMAIL, NAME, MOBILE, "maria", "Maria", "0000000123"):
                assert pii not in value


def test_line_item_names_the_court_sport_and_local_time():
    court = SimpleNamespace(name="Tennis Court 2")
    # Saturday 17 October 2026, 18:00–20:00 in Manila.
    starts_at = datetime(2026, 10, 17, 18, tzinfo=rules.TIME_ZONE)
    booking = SimpleNamespace(court=court, sport="tennis", starts_at=starts_at, hours=2)

    assert views.checkout_line_item(booking) == "Tennis Court 2 · Tennis · Sat 17 Oct, 6–8 PM"


@pytest.mark.django_db
def test_the_same_slot_twice_is_taken(client, fake):
    assert post(client, booking_body()).status_code == 201

    response = post(
        client,
        booking_body(customer=customer(email="other@example.com"), client_ip="203.0.113.11"),
    )

    assert response.status_code == 409
    assert response.json() == {"error": "slot_taken"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_sixth_create_from_one_ip_is_rate_limited(client, fake, monkeypatch):
    pin_ratelimit_clock(monkeypatch)
    for n in range(1, 6):
        response = post(
            client,
            booking_body(
                court=f"mp-{n:02d}", sport="badminton", customer=customer(email=f"p{n}@example.com")
            ),
        )
        assert response.status_code == 201

    response = post(
        client,
        booking_body(court="mp-06", sport="badminton", customer=customer(email="p6@example.com")),
    )

    assert response.status_code == 429
    assert response.json() == {"error": "rate_limited"}
    assert Booking.objects.count() == 5


def create_five(client, ips) -> None:
    """Five creates on distinct courts and emails, from the given IPs in turn."""
    for n in range(1, 6):
        response = post(
            client,
            booking_body(
                court=f"mp-{n:02d}",
                sport="badminton",
                customer=customer(email=f"p{n}@example.com"),
                client_ip=ips[n % len(ips)],
            ),
        )
        assert response.status_code == 201


@pytest.mark.django_db
@pytest.mark.parametrize(
    "ips",
    [
        pytest.param(("2001:db8:1:2::1", "2001:db8:1:2:ffff:ffff:ffff:fffe"), id="one-ipv6-64"),
        pytest.param(("::ffff:203.0.113.10", "203.0.113.10"), id="ipv4-mapped"),
    ],
)
def test_addresses_of_one_client_share_the_create_window(client, fake, monkeypatch, ips):
    pin_ratelimit_clock(monkeypatch)
    create_five(client, ips)

    response = post(
        client,
        booking_body(
            court="mp-06",
            sport="badminton",
            customer=customer(email="p6@example.com"),
            client_ip=ips[0],
        ),
    )

    assert response.status_code == 429
    assert response.json() == {"error": "rate_limited"}


@pytest.mark.django_db
def test_another_ipv6_64_has_its_own_window(client, fake, monkeypatch):
    pin_ratelimit_clock(monkeypatch)
    create_five(client, ("2001:db8:1:2::1",))

    response = post(
        client,
        booking_body(
            court="mp-06",
            sport="badminton",
            customer=customer(email="p6@example.com"),
            client_ip="2001:db8:1:3::1",
        ),
    )

    assert response.status_code == 201


@pytest.mark.django_db
@pytest.mark.parametrize("client_ip", ["fe80::1%eth0", "fe80::1%1", "203.0.113.10%1"])
def test_an_ip_with_a_zone_id_is_invalid(client, fake, client_ip):
    response = post(client, booking_body(client_ip=client_ip))

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request", "fields": ["client_ip"]}
    assert not fake.calls


@pytest.mark.django_db
def test_third_active_hold_for_one_email_is_refused(client, fake, monkeypatch):
    pin_ratelimit_clock(monkeypatch)
    for court in ("tn-1", "tn-2"):
        assert post(client, booking_body(court=court)).status_code == 201

    response = post(client, booking_body(court="tn-3", customer=customer(email=EMAIL.upper())))

    assert response.status_code == 429
    assert response.json() == {"error": "too_many_holds"}
    assert Booking.objects.count() == 2


@pytest.mark.django_db
def test_lapsed_holds_do_not_count_against_the_email(client, fake):
    for court in ("tn-1", "tn-2"):
        assert post(client, booking_body(court=court)).status_code == 201
    Booking.objects.update(hold_expires_at=timezone.now() - timedelta(minutes=1))

    assert post(client, booking_body(court="tn-3")).status_code == 201


@pytest.mark.django_db
def test_consent_must_be_true(client, fake):
    for consent in (False, "true", 1, None):
        response = post(client, booking_body(consent=consent))

        assert response.status_code == 400
        assert response.json() == {"error": "invalid_request", "fields": ["consent"]}
    assert not fake.calls
    assert not Booking.objects.exists()


@pytest.mark.django_db
def test_a_bad_mobile_is_named_but_never_echoed(client, fake):
    bad_mobile = "+15555550123"
    response = post(client, booking_body(customer=customer(mobile=bad_mobile)))

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request", "fields": ["customer.mobile"]}
    assert bad_mobile not in response.content.decode()
    assert NAME not in response.content.decode()


@pytest.mark.django_db
def test_a_mobile_with_non_ascii_digits_is_invalid(client, fake):
    # Arabic-Indic digits: `\d` would match them.
    response = post(client, booking_body(customer=customer(mobile="09١٢٣٤٥٦٧٨٩")))

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request", "fields": ["customer.mobile"]}
    assert not Booking.objects.exists()


@pytest.mark.django_db
def test_every_invalid_field_is_named(client, fake):
    response = post(
        client,
        {
            "court": "tn-1\x00",
            "sport": "chess",
            "coverage": "most",
            "date": "2026-02-30",
            "start_hour": "10",
            "hours": True,
            "customer": {"name": "Ana\x00", "email": "not-an-email", "mobile": "0917"},
            "consent": "yes",
            "client_ip": "999.1.1.1",
        },
    )

    assert response.status_code == 400
    assert response.json()["fields"] == [
        "court",
        "sport",
        "coverage",
        "date",
        "start_hour",
        "hours",
        "customer.name",
        "customer.email",
        "customer.mobile",
        "consent",
        "client_ip",
    ]
    assert "not-an-email" not in response.content.decode()


@pytest.mark.django_db
def test_a_one_letter_name_is_invalid(client, fake):
    response = post(client, booking_body(customer=customer(name=" x ")))

    assert response.status_code == 400
    assert response.json()["fields"] == ["customer.name"]


@pytest.mark.django_db
def test_an_inactive_court_is_invalid(client, fake):
    Court.objects.filter(code="tn-1").update(is_active=False)

    response = post(client, booking_body())

    assert response.status_code == 400
    assert response.json()["fields"] == ["court"]


@pytest.mark.django_db
def test_price_and_status_in_the_body_are_ignored(client, fake):
    response = post(client, booking_body(price_centavos=1, status="confirmed"))

    assert response.status_code == 201
    booking = Booking.objects.get(reference=response.json()["reference"])
    assert booking.status == Status.PENDING
    assert booking.price_centavos == pricing.quote("tennis", "full", tomorrow(), 10, 2)


@pytest.mark.django_db
def test_half_volleyball_breaks_a_rule(client, fake):
    response = post(client, booking_body(court="bb-1", sport="volleyball", coverage="half"))

    assert response.status_code == 400
    assert response.json() == {"error": "coverage_not_allowed"}
    assert not fake.calls


@pytest.mark.django_db
def test_a_body_that_is_not_a_json_object_is_invalid(client, fake):
    for body in ("not json", "[]", '"text"'):
        response = post(client, body)

        assert response.status_code == 400
        assert response.json() == {"error": "invalid_request", "fields": ["body"]}


@pytest.mark.django_db
def test_a_body_over_4_kb_is_too_large(client, fake):
    response = post(client, booking_body(padding="x" * 4096))

    assert response.status_code == 413
    assert response.json() == {"error": "too_large"}
    assert response["Cache-Control"] == "no-store"
    assert not Booking.objects.exists()


@pytest.mark.django_db
def test_get_is_not_allowed(client):
    response = client.get(URL, headers=AUTH)

    assert response.status_code == 405
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "error",
    [
        PayMongoError("PayMongo responded 502", 502, ("resource_failed",)),
        PayMongoError("PayMongo request failed"),
    ],
)
def test_a_paymongo_error_frees_the_slot(client, monkeypatch, caplog, error):
    caplog.set_level(logging.INFO)
    use_fake_paymongo(monkeypatch, error)

    response = post(client, booking_body())

    assert response.status_code == 503
    assert response.json() == {"error": "payments_unavailable"}
    failed = Booking.objects.get()
    assert failed.status == Status.EXPIRED
    assert not SlotLock.objects.filter(booking=failed).exists()
    assert f"booking.checkout_failed ref={failed.reference}" in caplog.text
    assert f"status={error.status}" in caplog.text
    for pii in (EMAIL, NAME, MOBILE):
        assert pii not in caplog.text

    # The slot is free again.
    use_fake_paymongo(monkeypatch)
    assert post(client, booking_body()).status_code == 201


@pytest.mark.django_db
def test_missing_paymongo_config_frees_the_slot(client, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    # The real `get_client`, which reads the (missing) key.
    monkeypatch.delenv("PAYMONGO_SECRET_KEY", raising=False)

    response = post(client, booking_body())

    assert response.status_code == 503
    assert response.json() == {"error": "payments_unavailable"}
    assert Booking.objects.get().status == Status.EXPIRED
    assert "key=PAYMONGO_SECRET_KEY" in caplog.text


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_paymongo_is_called_outside_a_transaction_after_the_hold_commits(client, monkeypatch):
    seen = {}

    class Recording(FakePayMongo):
        def create_checkout_session(self, **kwargs):
            seen["in_atomic_block"] = connection.in_atomic_block
            seen["booking_exists"] = Booking.objects.filter(pk=kwargs["booking_id"]).exists()
            return super().create_checkout_session(**kwargs)

    monkeypatch.setattr(views, "get_client", Recording())

    assert post(client, booking_body()).status_code == 201
    assert seen == {"in_atomic_block": False, "booking_exists": True}


@pytest.mark.django_db
def test_an_unexpected_checkout_error_frees_the_slot_and_propagates(client, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    use_fake_paymongo(monkeypatch, RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        post(client, booking_body())

    failed = Booking.objects.get()
    assert failed.status == Status.EXPIRED
    assert not SlotLock.objects.filter(booking=failed).exists()
    assert f"booking.checkout_failed ref={failed.reference} error=RuntimeError" in caplog.text

    use_fake_paymongo(monkeypatch)
    assert post(client, booking_body()).status_code == 201


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_failed_save_of_the_session_id_frees_the_slot(client, monkeypatch, caplog):
    """The session ID column is unique: a second fake hands out `cs_test123` again, so saving it
    fails after the checkout session exists."""
    caplog.set_level(logging.INFO)
    use_fake_paymongo(monkeypatch)
    assert post(client, booking_body()).status_code == 201
    use_fake_paymongo(monkeypatch)

    with pytest.raises(IntegrityError):
        post(client, booking_body(court="tn-2"))

    failed = Booking.objects.get(court__code="tn-2")
    assert failed.status == Status.EXPIRED
    assert not SlotLock.objects.filter(booking=failed).exists()
    assert f"booking.checkout_failed ref={failed.reference} error=IntegrityError" in caplog.text
    for pii in (EMAIL, NAME, MOBILE):
        assert pii not in caplog.text

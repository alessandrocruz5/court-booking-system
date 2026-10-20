import logging
from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError

from bookings import rules
from bookings.management.commands import nightly
from bookings.models import Booking, Court, SlotLock
from bookings.rules import Source, Status
from core import ratelimit
from core.models import RateLimit

# Monday 2 November 2026, 03:00 in Manila: when Cloud Scheduler triggers the job.
NOW = datetime(2026, 11, 2, 3, tzinfo=rules.TIME_ZONE)
EMAIL = "juan.delacruz@example.com"


def booking(*, court: Court, ended_days_ago: float, is_demo: bool = False, **fields) -> Booking:
    ends_at = NOW - timedelta(days=ended_days_ago)
    defaults = {
        "reference": f"KC-{Booking.objects.count():06d}",
        "court": court,
        "sport": "tennis",
        "starts_at": ends_at - timedelta(hours=1),
        "ends_at": ends_at,
        "hours": 1,
        "source": Source.ONLINE,
        "status": Status.CONFIRMED,
        "price_centavos": 50_000,
        "customer_name": "Juan Dela Cruz",
        "customer_email": EMAIL,
        "customer_mobile": "+639000000001",
        "consent_at": ends_at - timedelta(days=1),
        "payment_id": "pay_test_1",
        "payment_method": "gcash",
        "fee_centavos": 1_250,
        "net_centavos": 48_750,
        "paid_at": ends_at - timedelta(days=1),
        "is_demo": is_demo,
    }
    return Booking.objects.create(**(defaults | fields))


@pytest.fixture
def court() -> Court:
    return Court.objects.filter(kind="tennis").order_by("sort_order").first()


@pytest.fixture(autouse=True)
def no_demo_seed(monkeypatch):
    monkeypatch.delenv("ALLOW_DEMO_SEED", raising=False)


@pytest.mark.django_db
def test_stale_pending_hold_is_expired(court):
    hold = booking(
        court=court,
        ended_days_ago=-1,
        status=Status.PENDING,
        hold_expires_at=NOW - timedelta(minutes=1),
    )
    SlotLock.objects.create(booking=hold, court=court, space="F", starts_at=hold.starts_at)

    assert nightly.run(now=NOW) == 0

    hold.refresh_from_db()
    assert hold.status == Status.EXPIRED
    assert not SlotLock.objects.filter(booking=hold).exists()


@pytest.mark.django_db
def test_visitor_data_is_anonymized_seven_days_after_the_booking_ends(court):
    old = booking(court=court, ended_days_ago=8)
    recent = booking(court=court, ended_days_ago=6)
    demo_row = booking(court=court, ended_days_ago=8, is_demo=True)

    assert nightly.run(now=NOW) == 0

    old.refresh_from_db()
    assert (old.customer_name, old.customer_email, old.customer_mobile) == ("", None, None)
    assert old.anonymized_at == NOW
    # Financial and slot data stay.
    assert (old.price_centavos, old.fee_centavos, old.net_centavos) == (50_000, 1_250, 48_750)
    assert (old.payment_id, old.status, old.court_id) == ("pay_test_1", Status.CONFIRMED, court.pk)

    recent.refresh_from_db()
    assert recent.customer_email == EMAIL and recent.anonymized_at is None
    # Demo rows are regenerated, never anonymized.
    demo_row.refresh_from_db()
    assert demo_row.customer_email == EMAIL and demo_row.anonymized_at is None


@pytest.mark.django_db
def test_anonymize_is_idempotent(court):
    old = booking(court=court, ended_days_ago=8)
    assert nightly.anonymize(now=NOW) == 1
    assert nightly.anonymize(now=NOW + timedelta(days=1)) == 0
    old.refresh_from_db()
    assert old.anonymized_at == NOW


@pytest.mark.django_db
def test_old_rate_limit_rows_are_pruned_and_the_current_window_stays():
    utc_now = NOW.astimezone(UTC)
    ratelimit.hit("signin", "old", limit=5, window_seconds=600, now=utc_now - timedelta(hours=2))
    ratelimit.hit("signin", "new", limit=5, window_seconds=600, now=utc_now)

    assert nightly.run(now=NOW) == 0

    assert RateLimit.objects.count() == 1
    assert RateLimit.objects.get().window_start > utc_now - timedelta(minutes=10)


@pytest.mark.django_db
def test_expired_sessions_are_cleared():
    store = SessionStore()
    store.set_expiry(-1)
    store.save()

    assert nightly.run(now=NOW) == 0

    assert not Session.objects.exists()


@pytest.mark.django_db
def test_no_reseed_without_allow_demo_seed():
    assert nightly.run(now=NOW) == 0
    assert not Booking.objects.filter(is_demo=True).exists()


@pytest.mark.django_db
def test_reseed_with_allow_demo_seed(monkeypatch, caplog):
    monkeypatch.setenv("ALLOW_DEMO_SEED", "1")
    with caplog.at_level(logging.INFO, logger="cb"):
        assert nightly.run(now=NOW) == 0

    assert Booking.objects.filter(is_demo=True).count() > 1000
    assert not Booking.objects.filter(status=Status.PENDING).exists()
    assert "@example.com" not in caplog.text and "+63900000" not in caplog.text


@pytest.mark.django_db
def test_a_failing_step_is_logged_by_class_and_the_others_still_run(monkeypatch, court, caplog):
    def boom(**kwargs):
        raise RuntimeError(EMAIL)

    monkeypatch.setattr(nightly, "expire_stale_holds", boom)
    old = booking(court=court, ended_days_ago=8)

    with caplog.at_level(logging.INFO, logger="cb.nightly"):
        assert nightly.run(now=NOW) == 1

    old.refresh_from_db()
    assert old.anonymized_at == NOW
    assert "nightly.expire_holds failed error=RuntimeError" in caplog.text
    assert EMAIL not in caplog.text


@pytest.mark.django_db
def test_nightly_command_exits_1_when_a_step_fails(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError

    monkeypatch.setattr(nightly, "anonymize", boom)
    with pytest.raises(CommandError) as exc:
        call_command("nightly")
    assert exc.value.returncode == 1


@pytest.mark.django_db
def test_nightly_command_succeeds():
    call_command("nightly")


def test_seed_demo_refuses_without_allow_demo_seed():
    with pytest.raises(CommandError) as exc:
        call_command("seed_demo")
    assert exc.value.returncode == 2
    assert "ALLOW_DEMO_SEED=1" in str(exc.value)

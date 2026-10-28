import logging
from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from bookings import holds, rules
from bookings.checkin import CheckInError, check_in
from bookings.models import Booking, Court, SlotLock
from bookings.rules import Coverage, Source, Sport, Status

# Monday 2 November 2026, 10:00 in Manila.
NOW = datetime(2026, 11, 2, 10, tzinfo=rules.TIME_ZONE)
TODAY = date(2026, 11, 2)
CUSTOMER_NAME = "Juan Dela Cruz"
_refs = iter(range(1, 10_000))


def at(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=rules.TIME_ZONE)


def booking(*, day: date = TODAY, start_hour: int = 12, hours: int = 1, **overrides) -> Booking:
    """A confirmed walk-in on tn-1; override fields to break exactly one check-in rule."""
    fields = {
        "reference": f"KC-{next(_refs):06d}",
        "court": Court.objects.get(code="tn-1"),
        "sport": Sport.TENNIS,
        "coverage": Coverage.FULL,
        "starts_at": at(day, start_hour),
        "ends_at": at(day, start_hour) + timedelta(hours=hours),
        "hours": hours,
        "source": Source.WALK_IN,
        "status": Status.CONFIRMED,
        "price_centavos": 50_000,
        "customer_name": CUSTOMER_NAME,
    }
    fields.update(overrides)
    return Booking.objects.create(**fields)


@pytest.fixture
def owner():
    return get_user_model().objects.create_user("owner@example.com", password="x" * 16)


def assert_refused(target: Booking, code: str, *, by, now: datetime = NOW) -> None:
    with pytest.raises(CheckInError) as info:
        check_in(target, by=by, now=now)
    assert info.value.code == code
    target.refresh_from_db()
    assert target.checked_in_at is None
    assert target.checked_in_by is None


@pytest.mark.django_db
def test_check_in_sets_both_fields(owner, caplog):
    caplog.set_level(logging.INFO, logger="cb.bookings")
    target = booking()

    assert check_in(target, by=owner, now=NOW) is True

    assert (target.checked_in_at, target.checked_in_by) == (NOW, owner)
    target.refresh_from_db()
    assert target.checked_in_at == NOW
    assert target.checked_in_by_id == owner.pk
    assert target.status == Status.CONFIRMED
    assert f"booking.checked_in ref={target.reference}" in caplog.text
    for value in (CUSTOMER_NAME, "Juan", owner.username):
        assert value not in caplog.text


@pytest.mark.django_db
def test_check_in_during_the_booking(owner):
    target = booking(start_hour=9, hours=2)
    assert check_in(target, by=owner, now=NOW) is True


@pytest.mark.django_db
def test_check_in_twice_returns_false_and_keeps_the_first(owner):
    target = booking()
    assert check_in(target, by=owner, now=NOW) is True

    later = NOW + timedelta(minutes=30)
    other = get_user_model().objects.create_user("staff@example.com", password="x" * 16)
    assert check_in(target, by=other, now=later) is False

    target.refresh_from_db()
    assert target.checked_in_at == NOW
    assert target.checked_in_by_id == owner.pk


@pytest.mark.django_db
@pytest.mark.parametrize("status", [Status.PENDING, Status.EXPIRED, Status.CANCELLED])
def test_check_in_refuses_a_booking_that_is_not_confirmed(owner, status):
    extra = {"hold_expires_at": NOW + timedelta(minutes=20)} if status == Status.PENDING else {}
    assert_refused(booking(status=status, **extra), "not_confirmed", by=owner)


@pytest.mark.django_db
def test_check_in_refuses_a_block(owner):
    target = booking(source=Source.BLOCK, sport=None, price_centavos=0, note="Maintenance")
    assert_refused(target, "is_block", by=owner)


@pytest.mark.django_db
@pytest.mark.parametrize("day", [TODAY - timedelta(days=1), TODAY + timedelta(days=1)])
def test_check_in_refuses_another_day(owner, day):
    assert_refused(booking(day=day), "not_today", by=owner)


@pytest.mark.django_db
def test_check_in_uses_the_manila_date(owner):
    # 23:30 UTC on 1 November is 07:30 on 2 November in Manila.
    target = booking(start_hour=7, hours=2)
    assert check_in(target, by=owner, now=datetime(2026, 11, 1, 23, 30, tzinfo=UTC)) is True


@pytest.mark.django_db
@pytest.mark.parametrize("start_hour", [8, 9])
def test_check_in_refuses_a_booking_that_has_ended(owner, start_hour):
    # 08:00-09:00 ended an hour ago; 09:00-10:00 ends exactly now.
    assert_refused(booking(start_hour=start_hour), "ended", by=owner)


@pytest.mark.django_db
def test_check_in_judges_the_locked_row_not_the_callers_copy(owner):
    target = booking()
    # Cancelled meanwhile; the caller's object still says confirmed.
    Booking.objects.filter(pk=target.pk).update(status=Status.CANCELLED)
    assert target.status == Status.CONFIRMED

    assert_refused(target, "not_confirmed", by=owner)


@pytest.mark.django_db
def test_a_checked_in_booking_can_still_be_cancelled(owner):
    target = holds.create_staff_booking(
        source=Source.WALK_IN,
        court=Court.objects.get(code="tn-1"),
        sport=Sport.TENNIS,
        coverage=Coverage.FULL,
        half=None,
        day=TODAY,
        start_hour=12,
        hours=1,
        created_by=owner,
        now=NOW,
    )
    assert check_in(target, by=owner, now=NOW) is True

    assert holds.cancel_booking(target, by_role="owner", now=NOW) == Status.CANCELLED

    target.refresh_from_db()
    assert target.status == Status.CANCELLED
    assert target.cancelled_at == NOW
    assert target.checked_in_at == NOW
    assert SlotLock.objects.filter(booking=target).count() == 0


def booking_columns() -> set[str]:
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, "bookings_booking")
    return {column.name for column in description}


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_migration_0003_applies_on_top_of_0002():
    executor = MigrationExecutor(connection)
    executor.migrate([("bookings", "0002_courts")])
    assert {"checked_in_at", "checked_in_by_id"}.isdisjoint(booking_columns())

    executor.loader.build_graph()
    executor.migrate([("bookings", "0003_booking_check_in")])
    assert {"checked_in_at", "checked_in_by_id"} <= booking_columns()
    assert Court.objects.count() == 18

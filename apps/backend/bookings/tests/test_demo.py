"""Demo data. A full generation is a few thousand bookings, so each test generates as few times as
its claim needs, and the row checks share one generation."""

import random
from datetime import date, datetime, time, timedelta

import pytest
from django.db import transaction

from bookings import demo, holds, rules
from bookings.models import Booking, Court, SlotLock
from bookings.rules import CLOSE_HOUR, OPEN_HOUR, CourtKind, Source, Status

# Monday 2 November 2026, 03:00 in Manila: when the nightly job runs.
TODAY = date(2026, 11, 2)
NOW = datetime(2026, 11, 2, 3, tzinfo=rules.TIME_ZONE)
SEED = TODAY.isoformat()
DAYS = demo.DAYS_BACK + 1 + demo.DAYS_AHEAD


def rng() -> random.Random:
    return random.Random(SEED)  # noqa: S311


def generate() -> int:
    return demo.generate(today=TODAY, now=NOW, rng=rng())


def demo_keys() -> set[tuple[int, datetime, str | None]]:
    return set(Booking.objects.filter(is_demo=True).values_list("court_id", "starts_at", "sport"))


@pytest.mark.django_db
def test_same_seed_gives_the_same_bookings():
    first_count = generate()
    first = demo_keys()
    second_count = generate()

    assert first_count == second_count == len(first) > 0
    assert demo_keys() == first
    assert Booking.objects.filter(is_demo=True).count() == second_count


def check_customer_rows(customers: list[Booking]) -> None:
    for b in customers:
        assert b.customer_email.endswith("@example.com")
        assert b.customer_mobile.startswith("+63900000") and len(b.customer_mobile) == 13
        assert b.customer_name
        assert b.consent_at == b.created_at <= NOW
        assert b.price_centavos > 0

    online = [b for b in customers if b.source == Source.ONLINE]
    walk_ins = [b for b in customers if b.source == Source.WALK_IN]
    assert online and walk_ins
    for b in online:
        assert b.payment_method in demo.DEMO_FEE_RATES
        assert b.payment_id.startswith("pay_demo_")
        assert b.net_centavos == b.price_centavos - b.fee_centavos
        assert b.created_at < b.paid_at < NOW
        assert b.starts_at - b.paid_at >= timedelta(hours=1)
        # Paid within 72 h of the start, or, for a booking further out, within the last 72 h.
        assert b.starts_at - b.paid_at <= timedelta(hours=72) or (
            b.paid_at >= NOW - timedelta(hours=72, minutes=5)
        )
    for b in walk_ins:
        assert b.payment_method == "cash"
        assert b.fee_centavos is None and b.net_centavos is None and b.paid_at is None


def check_hours(rows: list[Booking]) -> None:
    first = datetime.combine(TODAY - timedelta(days=demo.DAYS_BACK), time(0), rules.TIME_ZONE)
    last = datetime.combine(TODAY + timedelta(days=demo.DAYS_AHEAD + 1), time(0), rules.TIME_ZONE)
    for b in rows:
        start, end = b.starts_at.astimezone(rules.TIME_ZONE), b.ends_at.astimezone(rules.TIME_ZONE)
        assert first <= start < last
        assert start.hour >= OPEN_HOUR
        assert end.date() == start.date() and end.hour <= CLOSE_HOUR
    for (starts_at,) in SlotLock.objects.filter(booking__is_demo=True).values_list("starts_at"):
        assert OPEN_HOUR <= starts_at.astimezone(rules.TIME_ZONE).hour < CLOSE_HOUR


@pytest.mark.django_db
def test_demo_rows_are_marked_realistic_and_within_opening_hours():
    count = generate()
    rows = list(Booking.objects.filter(is_demo=True))

    # Every demo row is confirmed, marked, and holds its slots; none is left pending.
    assert len(rows) == count
    assert all(b.status == Status.CONFIRMED and b.is_demo for b in rows)
    assert not Booking.objects.filter(status=Status.PENDING).exists()
    assert not Booking.objects.filter(is_demo=True, locks__isnull=True).exists()

    # Customer rows carry the demo markers; blocks carry no customer data.
    customers = [b for b in rows if b.source != Source.BLOCK]
    blocks = [b for b in rows if b.source == Source.BLOCK]
    assert customers and blocks
    check_customer_rows(customers)
    for b in blocks:
        assert b.sport is None and b.price_centavos == 0 and b.note
        assert not b.customer_name and b.customer_email is None and b.customer_mobile is None

    # Occupancy over the 37 days lands between 25% and 75% of court-hours.
    court_hours = DAYS * Court.objects.filter(is_active=True).count() * (CLOSE_HOUR - OPEN_HOUR)
    occupied = (
        SlotLock.objects.filter(booking__is_demo=True)
        .values_list("court_id", "starts_at")
        .distinct()
        .count()
    )
    assert 0.25 <= occupied / court_hours <= 0.75

    # No demo booking falls outside 07:00-23:00 or the today - 30 .. today + 6 window.
    check_hours(rows)


@pytest.mark.django_db
def test_real_booking_keeps_its_slot_and_a_skipped_demo_booking_leaves_nothing():
    courts = list(Court.objects.filter(is_active=True).order_by("sort_order"))
    planned = demo.plan(today=TODAY, courts=courts, rng=rng())
    target = next(
        p
        for p in planned
        if p.court.kind == CourtKind.TENNIS and p.source == Source.ONLINE and p.day > TODAY
    )
    real = holds.create_staff_booking(
        source=Source.WALK_IN,
        court=target.court,
        sport=target.sport,
        coverage=target.coverage,
        half=None,
        day=target.day,
        start_hour=target.start_hour,
        hours=1,
        created_by=None,
        customer_name="Real Visitor",
        now=NOW,
    )
    starts_at = rules.slot_starts(target.day, target.start_hour, 1)[0]
    # A real online hold that lapsed before the run, on another planned demo slot: its customer may
    # still pay late, so the seed must neither expire it nor take its slot.
    late = next(
        p
        for p in planned
        if p.court.kind == CourtKind.TENNIS
        and p.source == Source.ONLINE
        and p.day > TODAY
        and (p.court, p.day) != (target.court, target.day)
    )
    lapsed = holds.create_hold(
        court=late.court,
        sport=late.sport,
        coverage=late.coverage,
        day=late.day,
        start_hour=late.start_hour,
        hours=1,
        customer=holds.Customer(
            name="Late Payer", email="late.payer@example.com", mobile="+639000000002"
        ),
        now=NOW - timedelta(minutes=rules.HOLD_MINUTES + 10),
    )
    late_starts_at = rules.slot_starts(late.day, late.start_hour, 1)[0]
    old_demo = holds.create_staff_booking(
        source=Source.BLOCK,
        court=courts[-1],
        sport=None,
        coverage="full",
        half=None,
        day=TODAY,
        start_hour=12,
        hours=1,
        created_by=None,
        note="Old demo block",
        is_demo=True,
        now=NOW,
    )

    count = generate()

    real.refresh_from_db()
    assert real.status == Status.CONFIRMED and not real.is_demo
    assert set(SlotLock.objects.filter(court=target.court, starts_at=starts_at)) == set(
        real.locks.all()
    )
    # The lapsed hold is untouched and keeps its slot free of demo bookings, so a late payment can
    # still re-claim it.
    lapsed.refresh_from_db()
    assert lapsed.status == Status.PENDING
    assert set(SlotLock.objects.filter(court=late.court, starts_at=late_starts_at)) == set(
        lapsed.locks.all()
    )
    with transaction.atomic():
        assert holds.reacquire(lapsed, now=NOW)

    # The clashing demo bookings were skipped and left no booking row (nor locks) behind.
    assert count == len(planned) - 2
    assert Booking.objects.filter(is_demo=True).count() == count
    assert not Booking.objects.filter(is_demo=True, locks__isnull=True).exists()
    assert not Booking.objects.filter(
        is_demo=True, court=target.court, starts_at=starts_at
    ).exists()

    # Regenerating deleted the old demo rows, and only those.
    assert not Booking.objects.filter(pk=old_demo.pk).exists()
    assert set(Booking.objects.filter(is_demo=False)) == {real, lapsed}


def test_plan_mix_and_illustrative_fees():
    courts = [
        Court(pk=n, code=f"c{n}", name=f"C{n}", kind=kind, sort_order=n)
        for n, kind in enumerate(
            [CourtKind.BASKETBALL] * 2 + [CourtKind.TENNIS] * 4 + [CourtKind.MULTI] * 12
        )
    ]
    planned = demo.plan(today=TODAY, courts=courts, rng=rng())
    customers = [p for p in planned if p.source != Source.BLOCK]
    blocks = [p for p in planned if p.source == Source.BLOCK]
    online = sum(p.source == Source.ONLINE for p in customers) / len(customers)

    assert 0.75 <= online <= 0.85
    assert 4 <= len(blocks) <= 12
    assert all(1 <= p.hours <= 3 for p in planned)
    assert {p.sport for p in customers} == set(rules.Sport.values)
    assert demo.DEMO_FEE_RATES == {
        "gcash": (250, 0),
        "paymaya": (200, 0),
        "grab_pay": (220, 0),
        "card": (350, 1_500),
    }

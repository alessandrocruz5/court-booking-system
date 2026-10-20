import logging
import re
import threading
from datetime import date, datetime, timedelta

import pytest
from django.db import connection, transaction

from bookings import holds, references, rules
from bookings.holds import Customer, SlotTaken
from bookings.models import Booking, Court, SlotLock
from bookings.rules import BookingRuleError, Status

# Monday 2 November 2026, 10:00 in Manila.
NOW = datetime(2026, 11, 2, 10, tzinfo=rules.TIME_ZONE)
TOMORROW = date(2026, 11, 3)
LAPSED = NOW + timedelta(minutes=rules.HOLD_MINUTES)
CUSTOMER = Customer(
    name="Juan Dela Cruz", email="juan.delacruz@example.com", mobile="+639000000001"
)


def hold(
    code: str,
    sport: str,
    coverage: str = "full",
    *,
    start_hour: int = 12,
    hours: int = 1,
    now: datetime = NOW,
) -> Booking:
    return holds.create_hold(
        court=Court.objects.get(code=code),
        sport=sport,
        coverage=coverage,
        day=TOMORROW,
        start_hour=start_hour,
        hours=hours,
        customer=CUSTOMER,
        now=now,
    )


def staff(
    code: str,
    *,
    source: str = "walk_in",
    sport: str | None = "basketball",
    coverage: str = "full",
    half: str | None = None,
    note: str = "",
) -> Booking:
    return holds.create_staff_booking(
        source=source,
        court=Court.objects.get(code=code),
        sport=sport,
        coverage=coverage,
        half=half,
        day=TOMORROW,
        start_hour=12,
        hours=1,
        created_by=None,
        note=note,
        now=NOW,
    )


def lock_keys(booking: Booking) -> set[tuple[str, int]]:
    return {
        (space, starts_at.astimezone(rules.TIME_ZONE).hour)
        for space, starts_at in SlotLock.objects.filter(booking=booking).values_list(
            "space", "starts_at"
        )
    }


def test_reference_format():
    refs = {references.new_reference() for _ in range(200)}
    assert len(refs) == 200
    for ref in refs:
        assert re.fullmatch(r"KC-[0-9ABCDEFGHJKMNPQRSTVWXYZ]{6}", ref)


@pytest.mark.django_db
def test_create_hold_snapshots_a_pending_booking(caplog):
    caplog.set_level(logging.INFO, logger="cb.bookings")
    booking = hold("tn-1", "tennis", start_hour=16, hours=2)

    booking.refresh_from_db()
    assert booking.status == Status.PENDING
    assert booking.source == "online"
    assert booking.hold_expires_at == NOW + timedelta(minutes=20)
    assert booking.consent_at == NOW
    assert booking.price_centavos == 50_000 + 70_000
    assert booking.starts_at == datetime(2026, 11, 3, 16, tzinfo=rules.TIME_ZONE)
    assert booking.ends_at == datetime(2026, 11, 3, 18, tzinfo=rules.TIME_ZONE)
    assert (booking.customer_name, booking.customer_email, booking.customer_mobile) == (
        CUSTOMER.name,
        CUSTOMER.email,
        CUSTOMER.mobile,
    )
    assert lock_keys(booking) == {("F", 16), ("F", 17)}
    assert f"hold.created ref={booking.reference}" in caplog.text
    for value in (CUSTOMER.name, CUSTOMER.email, CUSTOMER.mobile, "juan"):
        assert value not in caplog.text


@pytest.mark.django_db
def test_create_hold_validates_first():
    with pytest.raises(BookingRuleError) as info:
        hold("tn-1", "badminton")
    assert info.value.code == "wrong_court_for_sport"
    assert Booking.objects.count() == 0


@pytest.mark.django_db
def test_half_holds_take_a_then_b_then_slot_taken():
    first = hold("bb-1", "basketball", "half")
    second = hold("bb-1", "basketball", "half")
    assert (first.half, second.half) == ("A", "B")
    assert lock_keys(first) == {("A", 12)}
    assert lock_keys(second) == {("B", 12)}

    with pytest.raises(SlotTaken):
        hold("bb-1", "basketball", "half")
    assert Booking.objects.count() == 2


@pytest.mark.django_db
def test_full_after_half_is_taken():
    hold("bb-1", "basketball", "half")
    with pytest.raises(SlotTaken):
        hold("bb-1", "volleyball")
    with pytest.raises(SlotTaken):
        hold("bb-1", "basketball")
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_half_after_full_is_taken():
    full = hold("bb-1", "basketball")
    assert lock_keys(full) == {("A", 12), ("B", 12)}
    with pytest.raises(SlotTaken):
        hold("bb-1", "basketball", "half")
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_overlapping_span_is_taken():
    hold("tn-1", "tennis", start_hour=13)
    with pytest.raises(SlotTaken):
        hold("tn-1", "tennis", start_hour=11, hours=3)
    hold("tn-1", "tennis", start_hour=11, hours=2)


@pytest.mark.django_db
def test_stale_hold_is_lazily_expired_and_slots_go_to_new_claimer():
    stale = hold("tn-1", "tennis", start_hour=12, hours=2)
    untouched = hold("tn-2", "tennis")

    with pytest.raises(SlotTaken):
        hold("tn-1", "tennis", start_hour=13, now=LAPSED - timedelta(seconds=1))

    fresh = hold("tn-1", "tennis", start_hour=13, now=LAPSED)

    stale.refresh_from_db()
    untouched.refresh_from_db()
    assert stale.status == Status.EXPIRED
    # All of the stale hold's locks go, including the 12:00 one the new claim didn't need.
    assert lock_keys(stale) == set()
    assert lock_keys(fresh) == {("F", 13)}
    # Lazy expiry only touches holds on the claimed keys.
    assert untouched.status == Status.PENDING
    assert lock_keys(untouched) == {("F", 12)}


@pytest.mark.django_db
def test_reference_clash_is_retried(monkeypatch):
    existing = hold("tn-1", "tennis")
    refs = iter([existing.reference, existing.reference, "KC-ZZZZZZ"])
    monkeypatch.setattr(holds, "new_reference", lambda: next(refs))

    booking = hold("tn-2", "tennis")
    assert booking.reference == "KC-ZZZZZZ"


@pytest.mark.django_db
def test_release_is_idempotent():
    booking = hold("tn-1", "tennis")

    assert holds.release(booking, status="cancelled", now=NOW) is True
    assert booking.status == Status.CANCELLED
    booking.refresh_from_db()
    assert booking.status == Status.CANCELLED
    assert booking.cancelled_at == NOW
    assert lock_keys(booking) == set()

    assert holds.release(booking, status="cancelled", now=LAPSED) is False
    assert holds.release(booking, status="needs_refund", now=LAPSED) is False
    booking.refresh_from_db()
    assert (booking.status, booking.cancelled_at) == (Status.CANCELLED, NOW)
    # The slot is free again.
    hold("tn-1", "tennis")


@pytest.mark.django_db
def test_release_confirmed_and_bad_status():
    booking = staff("tn-1", sport="tennis")
    with pytest.raises(ValueError):
        holds.release(booking, status="confirmed")
    assert holds.release(booking, status="needs_refund", now=NOW) is True
    booking.refresh_from_db()
    assert booking.status == Status.NEEDS_REFUND
    assert booking.cancelled_at is None


@pytest.mark.django_db
def test_expire_stale_holds_bulk_expires_and_frees_slots():
    a = hold("tn-1", "tennis")
    b = hold("bb-1", "basketball")
    c = hold("tn-2", "tennis", now=NOW + timedelta(minutes=10))
    confirmed = staff("tn-3", sport="tennis")

    assert holds.expire_stale_holds(now=LAPSED) == 2
    assert holds.expire_stale_holds(now=LAPSED) == 0

    statuses = dict(Booking.objects.values_list("pk", "status"))
    assert statuses[a.pk] == statuses[b.pk] == Status.EXPIRED
    assert statuses[c.pk] == Status.PENDING
    assert statuses[confirmed.pk] == Status.CONFIRMED
    assert set(SlotLock.objects.values_list("booking_id", flat=True)) == {c.pk, confirmed.pk}


@pytest.mark.django_db
def test_reacquire_reclaims_same_slots_when_free():
    booking = hold("bb-1", "basketball", "half", start_hour=12, hours=2)
    assert holds.expire_stale_holds(now=LAPSED) == 1
    booking.refresh_from_db()

    with transaction.atomic():
        assert holds.reacquire(booking, now=LAPSED) is True
    booking.refresh_from_db()
    assert booking.status == Status.EXPIRED  # the caller confirms it
    assert lock_keys(booking) == {("A", 12), ("A", 13)}


@pytest.mark.django_db
def test_reacquire_lapsed_pending_hold_still_holding_its_locks():
    booking = hold("tn-1", "tennis")
    assert holds.reacquire(booking, now=LAPSED) is True
    booking.refresh_from_db()
    assert booking.status == Status.PENDING
    assert lock_keys(booking) == {("F", 12)}


@pytest.mark.django_db
def test_reacquire_returns_false_when_taken():
    booking = hold("tn-1", "tennis", start_hour=12, hours=2)
    holds.expire_stale_holds(now=LAPSED)
    hold("tn-1", "tennis", start_hour=13, now=LAPSED)
    booking.refresh_from_db()

    assert holds.reacquire(booking, now=LAPSED) is False
    booking.refresh_from_db()
    assert booking.status == Status.EXPIRED
    assert lock_keys(booking) == set()


@pytest.mark.django_db
def test_reacquire_refuses_staff_or_final_bookings():
    with pytest.raises(ValueError):
        holds.reacquire(staff("tn-1", sport="tennis"), now=NOW)
    booking = hold("tn-2", "tennis")
    holds.release(booking, status="cancelled", now=NOW)
    with pytest.raises(ValueError):
        holds.reacquire(booking, now=NOW)


@pytest.mark.django_db
def test_walk_in_is_confirmed_and_priced_in_cash():
    booking = staff("bb-1", coverage="half", half="B")
    booking.refresh_from_db()
    assert booking.status == Status.CONFIRMED
    assert booking.source == "walk_in"
    assert booking.price_centavos == 70_000
    assert booking.payment_method == "cash"
    assert booking.hold_expires_at is None
    assert lock_keys(booking) == {("B", 12)}


@pytest.mark.django_db
def test_block_on_basketball_locks_both_halves():
    booking = staff(
        "bb-1", source="block", sport="basketball", coverage="half", half="A", note="Resurfacing"
    )
    booking.refresh_from_db()
    assert (booking.sport, booking.coverage, booking.half) == (None, "full", None)
    assert booking.price_centavos == 0
    assert booking.status == Status.CONFIRMED
    assert lock_keys(booking) == {("A", 12), ("B", 12)}

    with pytest.raises(SlotTaken):
        hold("bb-1", "basketball", "half")


@pytest.mark.django_db
def test_block_requires_a_note():
    with pytest.raises(ValueError):
        staff("tn-1", source="block", sport=None, note="  ")
    assert Booking.objects.count() == 0


@pytest.mark.django_db
def test_staff_booking_clashing_with_hold_is_taken():
    hold("tn-1", "tennis")
    with pytest.raises(SlotTaken):
        staff("tn-1", sport="tennis")
    assert Booking.objects.count() == 1


def race(threads_n: int, now: datetime) -> tuple[list[Booking], list[SlotTaken]]:
    """`threads_n` threads call create_hold for tn-1 at 12:00 tomorrow at the same moment."""
    court = Court.objects.get(code="tn-1")
    barrier = threading.Barrier(threads_n)
    won: list[Booking] = []
    taken: list[SlotTaken] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker():
        try:
            barrier.wait()
            booking = holds.create_hold(
                court=court,
                sport="tennis",
                coverage="full",
                day=TOMORROW,
                start_hour=12,
                hours=1,
                customer=CUSTOMER,
                now=now,
            )
            with lock:
                won.append(booking)
        except SlotTaken as exc:
            with lock:
                taken.append(exc)
        except BaseException as exc:  # surfaced in the main thread below
            with lock:
                errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(threads_n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    return won, taken


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_concurrent_holds_exactly_one_wins():
    won, taken = race(8, NOW)

    assert len(won) == 1
    assert len(taken) == 7
    assert Booking.objects.count() == 1
    assert list(SlotLock.objects.values_list("booking_id", flat=True)) == [won[0].pk]


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_concurrent_claims_over_a_stale_hold_exactly_one_wins():
    stale = hold("tn-1", "tennis")

    won, taken = race(8, LAPSED)

    assert len(won) == 1
    assert len(taken) == 7
    stale.refresh_from_db()
    assert stale.status == Status.EXPIRED
    assert list(SlotLock.objects.values_list("booking_id", flat=True)) == [won[0].pk]

"""Slot claims: payment holds, staff bookings, release, expiry and late-payment re-acquisition.

The `SlotLock` unique (court, space, starts_at) constraint is the only arbiter of who gets a slot:
every claim inserts its locks and treats an IntegrityError as "taken". Nothing here checks
availability first. Stale holds expire lazily, on exactly the keys a new claim needs, so a slot
frees up the moment its hold lapses even if the nightly job hasn't run.

No external calls happen in here: the API calls PayMongo after `create_hold` commits. Logs carry
the booking reference only, never customer data (RA 10173).
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import reduce
from operator import or_

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from bookings import pricing, rules
from bookings.models import Booking, Court, SlotLock
from bookings.references import new_reference
from bookings.rules import HOLD_MINUTES, Coverage, Half, Source, Status

logger = logging.getLogger("cb.bookings")

REFERENCE_ATTEMPTS = 5
RELEASE_STATUSES = (Status.CANCELLED, Status.EXPIRED, Status.NEEDS_REFUND)


@dataclass(frozen=True)
class Customer:
    name: str
    email: str
    mobile: str


class SlotTaken(Exception):
    """Another booking holds at least one of the requested (court, space, hour) slots."""


def _expire_locked(ids: list) -> None:
    """Expire bookings already locked with select_for_update and drop all their locks."""
    SlotLock.objects.filter(booking_id__in=ids).delete()
    Booking.objects.filter(pk__in=ids).update(status=Status.EXPIRED, updated_at=timezone.now())


def claim_slots(
    booking: Booking, spaces: list[str], starts: list[datetime], *, now: datetime
) -> None:
    """Insert one lock per (space, start) for `booking`. Must run inside `transaction.atomic()`.

    Raises `SlotTaken` if any lock clashes; the failed insert is rolled back to a savepoint.
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("claim_slots must run inside transaction.atomic()")
    keys = reduce(or_, (Q(space=space, starts_at=start) for space in spaces for start in starts))

    # Lazily expire stale holds sitting on exactly these keys. Lock the bookings in pk order so
    # two concurrent claims never wait on each other in opposite orders; the status/expiry filter
    # is re-checked under the lock, so a hold another claim already expired is skipped.
    stale = (
        SlotLock.objects.filter(keys, court_id=booking.court_id)
        .filter(booking__status=Status.PENDING, booking__hold_expires_at__lte=now)
        .exclude(booking_id=booking.pk)
        .values_list("booking_id", flat=True)
    )
    stale_ids = set(stale)
    if stale_ids:
        expired = list(
            Booking.objects.select_for_update()
            .filter(pk__in=stale_ids, status=Status.PENDING, hold_expires_at__lte=now)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        if expired:
            _expire_locked(expired)
            logger.info("hold.expired count=%d lazy=1", len(expired))

    locks = [
        SlotLock(booking=booking, court_id=booking.court_id, space=space, starts_at=start)
        for space in spaces
        for start in starts
    ]
    try:
        with transaction.atomic():
            SlotLock.objects.bulk_create(locks)
    except IntegrityError as exc:
        raise SlotTaken from exc


def _is_reference_clash(exc: IntegrityError) -> bool:
    diag = getattr(exc.__cause__, "diag", None)
    return "reference" in (getattr(diag, "constraint_name", None) or "")


def _insert_booking(**fields) -> Booking:
    """Create a booking with a fresh reference, retrying on a unique-reference clash."""
    for attempt in range(REFERENCE_ATTEMPTS):
        try:
            with transaction.atomic():
                return Booking.objects.create(reference=new_reference(), **fields)
        except IntegrityError as exc:
            if not _is_reference_clash(exc) or attempt == REFERENCE_ATTEMPTS - 1:
                raise
    raise AssertionError("unreachable")


def create_hold(
    *,
    court: Court,
    sport: str,
    coverage: str,
    day: date,
    start_hour: int,
    hours: int,
    customer: Customer,
    now: datetime | None = None,
) -> Booking:
    """Validate, quote and claim a 20-minute payment hold. Raises `BookingRuleError` or
    `SlotTaken`. Half coverage takes half A if free, else half B."""
    now = now or timezone.now()
    rules.validate_customer_request(
        court=court,
        sport=sport,
        coverage=coverage,
        day=day,
        start_hour=start_hour,
        hours=hours,
        now=now,
    )
    price = pricing.quote(sport, coverage, day, start_hour, hours)
    starts = rules.slot_starts(day, start_hour, hours)
    halves = [Half.A, Half.B] if coverage == Coverage.HALF else [None]

    with transaction.atomic():
        for half in halves:
            try:
                with transaction.atomic():
                    booking = _insert_booking(
                        court=court,
                        sport=sport,
                        coverage=coverage,
                        half=half,
                        starts_at=starts[0],
                        ends_at=starts[-1] + timedelta(hours=1),
                        hours=hours,
                        source=Source.ONLINE,
                        status=Status.PENDING,
                        price_centavos=price,
                        customer_name=customer.name,
                        customer_email=customer.email,
                        customer_mobile=customer.mobile,
                        consent_at=now,
                        hold_expires_at=now + timedelta(minutes=HOLD_MINUTES),
                    )
                    claim_slots(booking, rules.spaces_for(court, coverage, half), starts, now=now)
            except SlotTaken:
                continue
            logger.info("hold.created ref=%s", booking.reference)
            return booking
    raise SlotTaken


def create_staff_booking(
    *,
    source: str,
    court: Court,
    sport: str | None,
    coverage: str,
    half: str | None,
    day: date,
    start_hour: int,
    hours: int,
    created_by,
    customer_name: str = "",
    note: str = "",
    is_demo: bool = False,
    now: datetime | None = None,
) -> Booking:
    """A confirmed walk-in (priced, paid in cash) or block (no sport, no price, a required note;
    always full coverage, so a block on basketball takes both halves)."""
    now = now or timezone.now()
    if source == Source.BLOCK:
        if not note.strip():
            raise ValueError("a block needs a note")
        sport, coverage, half = None, Coverage.FULL, None
    elif source == Source.WALK_IN:
        if sport is None:
            raise ValueError("a walk-in needs a sport")
        if coverage != Coverage.HALF:
            half = None
    else:
        raise ValueError("staff bookings are walk_in or block")

    rules.validate_staff_request(
        court=court,
        sport=sport,
        coverage=coverage,
        day=day,
        start_hour=start_hour,
        hours=hours,
        now=now,
    )
    spaces = rules.spaces_for(court, coverage, half)
    starts = rules.slot_starts(day, start_hour, hours)
    walk_in = source == Source.WALK_IN

    with transaction.atomic():
        booking = _insert_booking(
            court=court,
            sport=sport,
            coverage=coverage,
            half=half,
            starts_at=starts[0],
            ends_at=starts[-1] + timedelta(hours=1),
            hours=hours,
            source=source,
            status=Status.CONFIRMED,
            price_centavos=pricing.quote(sport, coverage, day, start_hour, hours) if walk_in else 0,
            payment_method="cash" if walk_in else "",
            customer_name=customer_name,
            note=note,
            is_demo=is_demo,
            created_by=created_by,
        )
        claim_slots(booking, spaces, starts, now=now)
    logger.info("staff_booking.created ref=%s source=%s", booking.reference, source)
    return booking


def release(booking: Booking, *, status: str, now: datetime | None = None) -> bool:
    """Free a pending or confirmed booking's slots and set its final `status`. Idempotent: returns
    False, changing nothing, when the booking is already final."""
    if status not in RELEASE_STATUSES:
        raise ValueError("release status must be cancelled, expired or needs_refund")
    now = now or timezone.now()
    with transaction.atomic():
        locked = Booking.objects.select_for_update().get(pk=booking.pk)
        if locked.status not in (Status.PENDING, Status.CONFIRMED):
            return False
        SlotLock.objects.filter(booking_id=locked.pk).delete()
        locked.status = status
        if status == Status.CANCELLED:
            locked.cancelled_at = now
        locked.save(update_fields=["status", "cancelled_at", "updated_at"])
    booking.status = locked.status
    booking.cancelled_at = locked.cancelled_at
    logger.info("booking.released ref=%s status=%s", locked.reference, status)
    return True


def expire_stale_holds(*, now: datetime | None = None) -> int:
    """Expire every pending booking whose hold has lapsed and free its slots. Returns the count."""
    now = now or timezone.now()
    with transaction.atomic():
        ids = list(
            Booking.objects.select_for_update()
            .filter(status=Status.PENDING, hold_expires_at__lte=now)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        if ids:
            _expire_locked(ids)
    if ids:
        logger.info("hold.expired count=%d", len(ids))
    return len(ids)


def reacquire(booking: Booking, *, now: datetime | None = None) -> bool:
    """Re-claim an online booking's same court, spaces and hours after its hold lapsed (a late
    payment). True on success, False if the slots are taken. Never changes the status: the
    payment confirmation that calls this does. A lapsed `pending` booking's leftover locks are
    dropped and re-inserted in the same savepoint."""
    if booking.source != Source.ONLINE or booking.status not in (Status.EXPIRED, Status.PENDING):
        raise ValueError("only an expired or pending online booking can be reacquired")
    now = now or timezone.now()
    spaces = rules.spaces_for(booking.court, booking.coverage, booking.half)
    local_start = booking.starts_at.astimezone(rules.TIME_ZONE)
    starts = rules.slot_starts(local_start.date(), local_start.hour, booking.hours)
    try:
        with transaction.atomic():
            SlotLock.objects.filter(booking_id=booking.pk).delete()
            claim_slots(booking, spaces, starts, now=now)
    except SlotTaken:
        logger.info("hold.reacquire_failed ref=%s", booking.reference)
        return False
    logger.info("hold.reacquired ref=%s", booking.reference)
    return True

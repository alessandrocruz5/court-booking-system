"""Read-side booking queries: customer availability and the staff occupancy grid.

Availability is advisory only; the `SlotLock` unique constraint decides who gets a slot.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from bookings import pricing, rules
from bookings.models import Booking, Court, SlotLock
from bookings.rules import CLOSE_HOUR, OPEN_HOUR, SPORTS, TIME_ZONE, Coverage, Half, Status


def active_locks_q(now: datetime) -> Q:
    """Filter for `SlotLock` rows that still hold their slot: the booking is confirmed, or pending
    with an unexpired hold. Expired, cancelled and needs_refund bookings hold nothing."""
    return Q(booking__status=Status.CONFIRMED) | Q(
        booking__status=Status.PENDING, booking__hold_expires_at__gt=now
    )


@dataclass(frozen=True)
class StartOption:
    hour: int
    price_centavos: int
    peak: bool


@dataclass(frozen=True)
class CourtAvailability:
    code: str
    name: str
    starts: list[StartOption]


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(0), tzinfo=TIME_ZONE)
    return start, start + timedelta(days=1)


def _day_locks(day: date, now: datetime):
    start, end = _day_bounds(day)
    return SlotLock.objects.filter(active_locks_q(now), starts_at__gte=start, starts_at__lt=end)


def availability(
    *,
    day: date,
    sport: str,
    coverage: str,
    hours: int,
    now: datetime | None = None,
) -> list[CourtAvailability]:
    now = now or timezone.now()
    rules.validate_search(sport=sport, coverage=coverage, day=day, hours=hours, now=now)
    courts = list(
        Court.objects.filter(kind=SPORTS[sport].court_kind, is_active=True).order_by("sort_order")
    )
    taken = {
        (court_id, space, starts_at.astimezone(TIME_ZONE).hour)
        for court_id, space, starts_at in _day_locks(day, now)
        .filter(court__in=courts)
        .values_list("court_id", "space", "starts_at")
    }

    result = []
    for court in courts:
        if coverage == Coverage.HALF:
            options = [rules.spaces_for(court, coverage, half) for half in (Half.A, Half.B)]
        else:
            options = [rules.spaces_for(court, coverage, None)]
        starts = []
        for hour in range(OPEN_HOUR, CLOSE_HOUR - hours + 1):
            if rules.slot_starts(day, hour, 1)[0] <= now:
                continue
            span = range(hour, hour + hours)
            if any(
                all((court.pk, space, h) not in taken for space in spaces for h in span)
                for spaces in options
            ):
                starts.append(
                    StartOption(
                        hour=hour,
                        price_centavos=pricing.quote(sport, coverage, day, hour, hours),
                        peak=pricing.is_peak(day, hour),
                    )
                )
        result.append(CourtAvailability(code=court.code, name=court.name, starts=starts))
    return result


def occupancy(day: date, *, now: datetime | None = None) -> dict[tuple[int, str, int], Booking]:
    """`(court_id, space, local hour) -> Booking` for the day's active locks (staff grid)."""
    now = now or timezone.now()
    return {
        (lock.court_id, lock.space, lock.starts_at.astimezone(TIME_ZONE).hour): lock.booking
        for lock in _day_locks(day, now).select_related("booking", "court")
    }

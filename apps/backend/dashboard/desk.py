"""What the Front desk reads: a reference lookup, name suggestions, who is arriving and who is on
court, and today's numbers.

Like `dashboard.queries`, every function takes the viewer's `Role` and returns rows already masked
for it (RA 10173), through `queries.name_for`, `mask_email` and `mask_mobile`. The derived status
comes from `queries.status_key`, and the overview's aggregates are reused, never re-derived.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.db.models import Q

from accounts.roles import Role, can_check_in, can_see_personal_data
from bookings.models import Booking
from bookings.references import ALPHABET, LENGTH, PREFIX
from bookings.rules import HOLD_MINUTES, TIME_ZONE, Source, Sport, Status, local_today

from .queries import (
    _SOLD,
    MAX_QUERY_LENGTH,
    SPACE_COUNT,
    STATUS_CHOICES,
    UPCOMING_HOURS,
    _alerts,
    _checked_in_clock,
    _clock,
    _lock_counts,
    _midnight,
    _search,
    _today,
    mask_email,
    mask_mobile,
    name_for,
    peso,
    status_key,
)

STATUS_LABELS = {**dict(STATUS_CHOICES), "block": "Blocked"}


@dataclass(frozen=True)
class DeskResult:
    reference: str
    status_key: str  # See `queries.status_key`.
    status_label: str
    pill: str  # "pill-<status_key>", the pill's CSS class.
    name: str  # The personal fields are masked for the viewer.
    contact: str  # Email and mobile, joined with " · ".
    amount: str  # Empty for a block.
    court: str
    sport: str  # "Basketball · full"; empty for a block.
    time: str  # "8 PM – 10 PM", prefixed "Fri 30, " when the booking isn't today.
    warning: str | None
    can_check_in: bool
    checked_in_clock: str  # "6:55 PM", or empty.
    schedule_day: date  # The day "View in schedule" opens.


@dataclass(frozen=True)
class Suggestion:
    reference: str
    name: str  # Masked for the viewer.
    when: str  # "Today, 8 PM – 10 PM" or "Fri 30, 8 PM – 10 PM".


@dataclass(frozen=True)
class DeskRow:
    """A row of "Arriving next" or "On court now"."""

    reference: str
    status_key: str
    name: str  # Masked for the viewer.
    court: str
    sport: str  # The value, for the tag's CSS class.
    starts: str  # "7 PM"
    ends: str  # "9 PM"
    tag: str  # "late" (it has started), "next" (it starts within the hour) or empty.
    can_check_in: bool
    is_demo: bool


@dataclass(frozen=True)
class DeskStats:
    bookings: int
    walk_ins: int
    revenue: int
    spaces_in_use: int  # Sold spaces in the current hour.
    space_count: int
    active_holds: int

    @property
    def revenue_display(self) -> str:
        return peso(self.revenue)


def normalise_query(text: str | None) -> str:
    """Trimmed and uppercased; `W3PE7U` becomes `KC-W3PE7U`. A NUL makes it empty (Postgres
    refuses one in a string)."""
    text = (text or "").strip().upper()[:MAX_QUERY_LENGTH]
    if "\x00" in text:
        return ""
    if "-" not in text and len(text) == LENGTH and all(ch in ALPHABET for ch in text):
        return PREFIX + text
    return text


def _hour(moment: datetime) -> str:
    """`8 PM`, or `8:30 PM` off the hour."""
    local = moment.astimezone(TIME_ZONE)
    return local.strftime("%I %p").lstrip("0") if local.minute == 0 else _clock(moment)


def _span(booking: Booking) -> str:
    return f"{_hour(booking.starts_at)} – {_hour(booking.ends_at)}"


def _day_prefix(booking: Booking, today: date) -> str:
    """`Fri 30, ` when the booking isn't on `today`, else empty."""
    start = booking.starts_at.astimezone(TIME_ZONE)
    return "" if start.date() == today else f"{start:%a} {start.day}, "


def _contact(role: Role | None, booking: Booking) -> str:
    if can_see_personal_data(role):
        parts = (booking.customer_email, booking.customer_mobile)
    else:
        parts = (mask_email(booking.customer_email), mask_mobile(booking.customer_mobile))
    return " · ".join(part for part in parts if part)


def _sport(booking: Booking) -> str:
    if not booking.sport:
        return ""
    coverage = f"half {booking.half}" if booking.half else "full"
    return f"{Sport(booking.sport).label} · {coverage}"


def _warning(booking: Booking, now: datetime) -> str | None:
    """The first that applies: not today, unpaid, running late, ended. A block has none."""
    if booking.source == Source.BLOCK:
        return None
    start = booking.starts_at.astimezone(TIME_ZONE)
    if booking.status == Status.CONFIRMED and start.date() != local_today(now):
        return f"This booking is for {start:%A} {start.day} {start:%b} — not today."
    if booking.status == Status.PENDING:
        # Holds lapse lazily, so a pending row can outlive its hold.
        if booking.hold_expires_at and booking.hold_expires_at > now:
            return f"Payment not received yet. The slot is on a {HOLD_MINUTES}-minute hold."
        return "Payment not received, and the hold has lapsed."
    if booking.status != Status.CONFIRMED:
        return None
    if booking.starts_at < now < booking.ends_at and booking.checked_in_at is None:
        return (
            f"Running late — started at {_hour(booking.starts_at)}. Ends {_hour(booking.ends_at)}."
        )
    if booking.ends_at <= now:
        return "This session has already ended."
    return None


def lookup(role: Role | None, text: str | None, now: datetime) -> DeskResult | None:
    """The booking whose reference is exactly `text` (normalised), masked for `role`; None when
    there is none."""
    reference = normalise_query(text)
    if not reference:
        return None
    booking = Booking.objects.select_related("court").filter(reference=reference).first()
    if booking is None:
        return None
    key = status_key(booking, now)
    return DeskResult(
        reference=booking.reference,
        status_key=key,
        status_label=STATUS_LABELS[key],
        pill=f"pill-{key}",
        name=name_for(role, booking.customer_name),
        contact=_contact(role, booking),
        amount="" if booking.source == Source.BLOCK else peso(booking.price_centavos),
        court=booking.court.name,
        sport=_sport(booking),
        time=_day_prefix(booking, local_today(now)) + _span(booking),
        warning=_warning(booking, now),
        can_check_in=can_check_in(role, booking, now=now),
        checked_in_clock=_checked_in_clock(booking),
        schedule_day=booking.starts_at.astimezone(TIME_ZONE).date(),
    )


def suggest(role: Role | None, text: str | None, now: datetime, limit: int = 5):
    """Up to `limit` of today's and later bookings (never blocks) matching `text`, earliest first.
    The match is `queries._search`, so the viewer matches names on demo bookings only. It needs 2
    characters, as the desk's input does."""
    text = (text or "").strip()[:MAX_QUERY_LENGTH]
    if len(text) < 2 or "\x00" in text:
        return ()
    today = local_today(now)
    bookings = (
        Booking.objects.select_related("court")
        .filter(_search(role, text), starts_at__gte=_midnight(today))
        .exclude(source=Source.BLOCK)
        .order_by("starts_at", "reference")[:limit]
    )
    return tuple(
        Suggestion(
            reference=booking.reference,
            name=name_for(role, booking.customer_name),
            when=(_day_prefix(booking, today) or "Today, ") + _span(booking),
        )
        for booking in bookings
    )


def _desk_row(role: Role | None, booking: Booking, now: datetime) -> DeskRow:
    if booking.starts_at < now:
        tag = "late"
    elif booking.starts_at <= now + timedelta(hours=1):
        tag = "next"
    else:
        tag = ""
    return DeskRow(
        reference=booking.reference,
        status_key=status_key(booking, now),
        name=name_for(role, booking.customer_name),
        court=booking.court.name,
        sport=booking.sport,
        starts=_hour(booking.starts_at),
        ends=_hour(booking.ends_at),
        tag=tag,
        can_check_in=can_check_in(role, booking, now=now),
        is_demo=booking.is_demo,
    )


def _today_sold(now: datetime):
    start = _midnight(local_today(now))
    return Booking.objects.select_related("court").filter(
        _SOLD, starts_at__gte=start, starts_at__lt=start + timedelta(days=1)
    )


def arriving(
    role: Role | None, now: datetime, within_hours: int = UPCOMING_HOURS
) -> tuple[DeskRow, ...]:
    """Today's confirmed bookings not on court and not ended, starting within `within_hours`
    (late ones included), earliest first. One checked in early stays here until it starts."""
    bookings = (
        _today_sold(now)
        .filter(
            Q(checked_in_at__isnull=True) | Q(starts_at__gt=now),
            ends_at__gt=now,
            starts_at__lt=now + timedelta(hours=within_hours),
        )
        .order_by("starts_at", "court__sort_order", "reference")
    )
    return tuple(_desk_row(role, booking, now) for booking in bookings)


def on_court(role: Role | None, now: datetime) -> tuple[DeskRow, ...]:
    """Today's checked-in bookings that have started and haven't ended."""
    bookings = (
        _today_sold(now)
        .filter(checked_in_at__isnull=False, starts_at__lte=now, ends_at__gt=now)
        .order_by("ends_at", "court__sort_order", "reference")
    )
    return tuple(_desk_row(role, booking, now) for booking in bookings)


def stats(now: datetime) -> DeskStats:
    """Today's bookings, walk-ins and revenue, the spaces sold this hour, and the live holds."""
    today = _today(now)
    hour = now.astimezone(TIME_ZONE).replace(minute=0, second=0, microsecond=0)
    locks = _lock_counts(hour, hour + timedelta(hours=1))
    return DeskStats(
        bookings=today.bookings,
        walk_ins=_today_sold(now).filter(source=Source.WALK_IN).count(),
        revenue=today.revenue,
        spaces_in_use=locks.get(Source.ONLINE, 0) + locks.get(Source.WALK_IN, 0),
        space_count=SPACE_COUNT,
        active_holds=_alerts(now).active_holds,
    )

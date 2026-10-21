"""The schedule screen's data: the day grid and the booking side panel.

Like `dashboard.queries`, this is the only place the schedule reads from, and everything it
returns is already masked for the viewer's role (RA 10173). Views and templates never mask.

The grid has one row per court in `sort_order`, and two for a basketball court (Half A and Half
B), by hour from opening to closing. A booking is one segment per row, spanning its consecutive
hours (`colspan`), so a full-court basketball booking appears in both half rows. Only active
locks show (`bookings.availability.occupancy`): confirmed bookings and live payment holds.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.utils import timezone

from accounts.roles import Role, can_cancel, can_create_staff_booking, can_see_personal_data
from bookings.availability import occupancy
from bookings.holds import refunds_on_cancel
from bookings.models import Booking, Court
from bookings.rules import (
    CLOSE_HOUR,
    OPEN_HOUR,
    SPACES,
    STAFF_WINDOW_DAYS,
    TIME_ZONE,
    Source,
    Sport,
    Status,
    local_today,
    slot_starts,
)

from .queries import SOURCE_LABELS, mask_email, mask_mobile, name_for, peso

# The demo viewer can add bookings from today to today + 6 (the storefront's window).
VIEWER_DAYS_AHEAD = 6
# How far back and ahead the schedule can be browsed.
BROWSE_DAYS = STAFF_WINDOW_DAYS

FREE = "free"
BOOKING = "booking"
_SLOT_CLASSES = {
    Source.ONLINE: "slot-online",
    Source.WALK_IN: "slot-walkin",
    Source.BLOCK: "slot-block",
}


def hour_label(hour: int) -> str:
    """`7` -> `7 AM`, `12` -> `12 PM`, `18` -> `6 PM`."""
    return f"{(hour - 1) % 12 + 1} {'AM' if hour < 12 else 'PM'}"


@dataclass(frozen=True)
class Cell:
    hour: int
    state: str  # FREE or BOOKING.
    past: bool  # The hour (or, for a booking, its last hour) has ended.
    label: str  # The accessible label of the cell's button.
    colspan: int = 1
    addable: bool = False  # A free cell the role may add a booking to.
    reference: str = ""
    source: str = ""
    status: str = ""
    is_demo: bool = False
    sport: str = ""  # Label, e.g. "Tennis"; empty for a block.
    name: str = ""  # Masked for the viewer.
    text: str = ""  # What the cell shows.
    can_cancel: bool = False

    @property
    def css(self) -> str:
        if self.state == FREE:
            return "slot-past" if self.past else "slot-free"
        classes = [_SLOT_CLASSES[self.source]]
        if self.status == Status.PENDING:
            classes.append("slot-pending")
        return " ".join(classes)


@dataclass(frozen=True)
class Row:
    label: str  # "Tennis Court 2" or "Basketball Court 1 · Half A".
    court_code: str
    space: str  # "F", "A" or "B".
    cells: tuple[Cell, ...]


@dataclass(frozen=True)
class Grid:
    day: date
    today: date
    hours: tuple[str, ...]  # Column headers.
    rows: tuple[Row, ...]
    prev_day: date | None  # None at the edge of the browsable range.
    next_day: date | None
    min_day: date
    max_day: date

    @property
    def is_today(self) -> bool:
        return self.day == self.today


@dataclass(frozen=True)
class BookingDetail:
    reference: str
    court: str
    coverage: str  # "Full court", "Half A" or "Half B".
    sport: str
    when: str
    source: str
    status: str
    is_demo: bool
    name: str  # The personal fields are masked for the viewer.
    email: str
    mobile: str
    price: str
    payment_method: str
    note: str
    can_cancel: bool
    refund_note: bool  # The owner cancelling a paid online booking refunds it in PayMongo.


def browse_bounds(now: datetime) -> tuple[date, date]:
    today = local_today(now)
    return today - timedelta(days=BROWSE_DAYS), today + timedelta(days=BROWSE_DAYS)


def _hour_ended(day: date, hour: int, now: datetime) -> bool:
    return slot_starts(day, hour, 1)[0] + timedelta(hours=1) <= now


def can_add_on(role: Role | None, day: date, now: datetime) -> bool:
    """Whether `role` may add a booking on `day` at all (the hour still has to be open)."""
    if not can_create_staff_booking(role):
        return False
    today = local_today(now)
    last = today + timedelta(days=VIEWER_DAYS_AHEAD if role == Role.VIEWER else STAFF_WINDOW_DAYS)
    return today <= day <= last


def _text(booking: Booking, name: str) -> str:
    if booking.source == Source.BLOCK:
        return booking.note or "Block"
    return name or Sport(booking.sport).label


def _booking_cell(row_label: str, booking: Booking, start: int, end: int, *, role, day, now):
    name = "" if booking.source == Source.BLOCK else name_for(role, booking.customer_name)
    source = SOURCE_LABELS[booking.source].lower()
    pending = ", payment pending" if booking.status == Status.PENDING else ""
    who = f", {name}" if name else ""
    return Cell(
        hour=start,
        state=BOOKING,
        past=_hour_ended(day, end - 1, now),
        label=(
            f"{row_label}, {hour_label(start)} to {hour_label(end)}, "
            f"{source}{pending}{who}: details"
        ),
        colspan=end - start,
        reference=booking.reference,
        source=booking.source,
        status=booking.status,
        is_demo=booking.is_demo,
        sport=Sport(booking.sport).label if booking.sport else "",
        name=name,
        text=_text(booking, name),
        can_cancel=can_cancel(role, booking),
    )


def _row(court: Court, space: str, taken: dict, *, role, day, now, addable_day) -> Row:
    label = court.name if space == "F" else f"{court.name} · Half {space}"
    cells = []
    hour = OPEN_HOUR
    while hour < CLOSE_HOUR:
        booking = taken.get((court.pk, space, hour))
        if booking is None:
            past = _hour_ended(day, hour, now)
            cells.append(
                Cell(
                    hour=hour,
                    state=FREE,
                    past=past,
                    label=f"{label}, {hour_label(hour)}, free: add booking",
                    addable=addable_day and not past,
                )
            )
            hour += 1
            continue
        end = hour + 1
        while end < CLOSE_HOUR and getattr(taken.get((court.pk, space, end)), "pk", None) == (
            booking.pk
        ):
            end += 1
        cells.append(_booking_cell(label, booking, hour, end, role=role, day=day, now=now))
        hour = end
    return Row(label=label, court_code=court.code, space=space, cells=tuple(cells))


def build_grid(day: date, *, role: Role | None, now: datetime | None = None) -> Grid:
    """The day's schedule grid for `role`. `now` is injectable so tests can pin the clock."""
    now = now or timezone.now()
    taken = occupancy(day, now=now)
    addable_day = can_add_on(role, day, now)
    rows = []
    for court in Court.objects.filter(is_active=True).order_by("sort_order"):
        for space in SPACES[court.kind]:  # Basketball: A and B; the rest: F.
            rows.append(
                _row(court, space, taken, role=role, day=day, now=now, addable_day=addable_day)
            )
    first, last = browse_bounds(now)
    return Grid(
        day=day,
        today=local_today(now),
        hours=tuple(hour_label(hour) for hour in range(OPEN_HOUR, CLOSE_HOUR)),
        rows=tuple(rows),
        prev_day=day - timedelta(days=1) if day > first else None,
        next_day=day + timedelta(days=1) if day < last else None,
        min_day=first,
        max_day=last,
    )


def get_booking(reference: str) -> Booking | None:
    """The booking with `reference`, for a permission check and a write through `bookings.holds`."""
    return Booking.objects.select_related("court").filter(reference=reference).first()


def viewer_live_bookings(user, now: datetime) -> int:
    """How many confirmed demo bookings `user` made that haven't ended yet: the demo viewer's
    quota. A count, not a slot check: slots are only ever claimed through `bookings.holds`."""
    return Booking.objects.filter(
        created_by=user, is_demo=True, status=Status.CONFIRMED, ends_at__gt=now
    ).count()


def _clock(moment: datetime) -> str:
    return moment.astimezone(TIME_ZONE).strftime("%I:%M %p").lstrip("0")


def booking_detail(booking: Booking, *, role: Role | None) -> BookingDetail:
    """The side panel's view of `booking`, masked for `role`."""
    raw = can_see_personal_data(role)
    start = booking.starts_at.astimezone(TIME_ZONE)
    # A walk-in's note is free text a staff member typed, so only the owner sees it; a block's
    # note is its reason (maintenance, an event) and is shown to everyone.
    show_note = booking.source == Source.BLOCK or raw
    cancellable = can_cancel(role, booking)
    return BookingDetail(
        reference=booking.reference,
        court=booking.court.name,
        coverage=f"Half {booking.half}" if booking.half else "Full court",
        sport=Sport(booking.sport).label if booking.sport else "",
        when=f"{start:%a} {start.day} {start:%b}, {_clock(booking.starts_at)} - "
        f"{_clock(booking.ends_at)}",
        source=SOURCE_LABELS[booking.source],
        status=Status(booking.status).label,
        is_demo=booking.is_demo,
        name=name_for(role, booking.customer_name),
        email=(booking.customer_email or "") if raw else mask_email(booking.customer_email),
        mobile=(booking.customer_mobile or "") if raw else mask_mobile(booking.customer_mobile),
        price=peso(booking.price_centavos),
        payment_method=booking.payment_method,
        note=booking.note if show_note else "",
        can_cancel=cancellable,
        refund_note=cancellable and role == Role.OWNER and refunds_on_cancel(booking),
    )

"""The schedule screen's data: the day grid and the booking side panel.

Like `dashboard.queries`, this is the only place the schedule reads from, and everything it
returns is already masked for the viewer's role (RA 10173). Views and templates never mask.

The grid has one row per court in `sort_order`, and two for a basketball court (Half A and Half
B), by hour from opening to closing. A booking is one segment per row, spanning its consecutive
hours (`colspan`), so a full-court basketball booking appears in both half rows. Only active
locks show (`bookings.availability.occupancy`): confirmed bookings and live payment holds.

The template draws the day as a CSS grid (`Grid.blocks`, `Grid.empty_cells`, `Grid.groups`), placed
by line numbers: row 1 is the hour header, column 1 the court names, and `FIRST_COL` is the first
hour. The rows are the segments above, grouped; a booking that holds both basketball halves is one
block spanning both rows.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.utils import timezone

from accounts.roles import (
    Role,
    can_cancel,
    can_check_in,
    can_create_staff_booking,
    can_see_personal_data,
)
from bookings.availability import occupancy
from bookings.holds import refunds_on_cancel
from bookings.models import Booking, Court
from bookings.rules import (
    CLOSE_HOUR,
    OPEN_HOUR,
    SPACES,
    STAFF_WINDOW_DAYS,
    TIME_ZONE,
    CourtKind,
    Source,
    Sport,
    Status,
    local_today,
    slot_starts,
)

from .desk import STATUS_LABELS
from .queries import (
    CHECKED_IN,
    COMPLETED,
    SOURCE_LABELS,
    _checked_in_clock,
    mask_email,
    mask_mobile,
    name_for,
    peso,
    status_key,
)

# The demo viewer can add bookings from today to today + 6 (the storefront's window).
VIEWER_DAYS_AHEAD = 6
# How far back and ahead the schedule can be browsed.
BROWSE_DAYS = STAFF_WINDOW_DAYS

FREE = "free"
BOOKING = "booking"
# The grid column of OPEN_HOUR: column 1 holds the court names.
FIRST_COL = 2
GROUP_LABELS = {
    CourtKind.BASKETBALL: "Basketball · Volleyball",
    CourtKind.TENNIS: "Tennis",
    CourtKind.MULTI: "Multi-courts · Badminton & Pickleball",
}
# `queries.status_key` -> a block's state. A confirmed booking is `walk_in` or `online` by source.
_BLOCK_STATES = {
    COMPLETED: "done",
    CHECKED_IN: "checked_in",
    Source.BLOCK: "block",
    Status.PENDING: "pending",
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
    block_state: str = ""  # See `Block.state`; empty for a free cell.
    sub: str = ""  # The second line of the booking's block: sport, half and reference.


@dataclass(frozen=True)
class Row:
    label: str  # "Tennis Court 2" or "Basketball Court 1 · Half A".
    court_code: str
    space: str  # "F", "A" or "B".
    cells: tuple[Cell, ...]
    grid_row: int  # The row's line in the CSS grid.
    name: str  # The court's name: "Tennis Court 2" or "Basketball Court 1".
    half: str  # "Half A" or "Half B" on a basketball court; empty otherwise.


@dataclass(frozen=True)
class Group:
    """A heading row between the court rows: "Tennis", for instance."""

    label: str
    row: int


@dataclass(frozen=True)
class HourHead:
    label: str
    col: int
    past: bool  # The hour has ended.
    current: bool  # It is this hour now (today only).


@dataclass(frozen=True)
class EmptyCell:
    """A free hour on one row: a button when `addable`, else inert (`past` or out of range)."""

    row: int
    col: int
    court_code: str
    space: str
    hour: int
    past: bool
    addable: bool
    label: str  # The accessible label of the cell's button.


@dataclass(frozen=True)
class Block:
    """One booking on one court. A booking that holds both basketball halves (a full-court
    booking, or a block) is one block spanning both rows."""

    reference: str
    row: int
    row_span: int  # 1, or 2 for a booking on both halves.
    col: int
    col_span: int  # Hours.
    state: str  # online, checked_in, walk_in, pending, block or done.
    name: str  # Masked for the viewer.
    sub: str
    label: str  # The accessible label of the block's button.


@dataclass(frozen=True)
class Grid:
    day: date
    today: date
    hour_heads: tuple[HourHead, ...]  # Column headers.
    groups: tuple[Group, ...]
    rows: tuple[Row, ...]
    blocks: tuple[Block, ...]
    empty_cells: tuple[EmptyCell, ...]
    now_col: int | None  # The current hour's column; None unless today and the venue is open.
    now_minute_class: str  # "now-m-45": where in that column the marker sits.
    now_label: str  # "7:48".
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
    can_check_in: bool
    status_key: str  # See `queries.status_key`; `status` is its label.
    checked_in_clock: str  # "6:55 PM", or empty.


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


def block_state(booking: Booking, now: datetime) -> str:
    """The look of `booking`'s block, from `queries.status_key`, the one rule for a status."""
    state = _BLOCK_STATES.get(status_key(booking, now))
    if state:
        return state
    return "walk_in" if booking.source == Source.WALK_IN else "online"


def _sub(booking: Booking) -> str:
    """The block's second line: `Basketball · half · KC-AB12CD`, or `Blocked · KC-AB12CD`."""
    if booking.source == Source.BLOCK:
        return f"Blocked · {booking.reference}"
    half = " · half" if booking.half else ""
    return f"{Sport(booking.sport).label}{half} · {booking.reference}"


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
        can_cancel=can_cancel(role, booking, now=now),
        block_state=block_state(booking, now),
        sub=_sub(booking),
    )


def _row(
    court: Court, space: str, taken: dict, *, role, day, now, addable_day, grid_row: int
) -> Row:
    half = "" if space == "F" else f"Half {space}"
    label = f"{court.name} · {half}" if half else court.name
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
    return Row(
        label=label,
        court_code=court.code,
        space=space,
        cells=tuple(cells),
        grid_row=grid_row,
        name=court.name,
        half=half,
    )


def _blocks(court: Court, rows: list[Row]) -> list[Block]:
    """The court's bookings as blocks. A booking on both halves is in both rows' cells but is one
    block, starting in the first row and spanning them all."""
    rows_of = Counter(cell.reference for row in rows for cell in row.cells if cell.reference)
    blocks = {}
    for row in rows:
        for cell in row.cells:
            if not cell.reference or cell.reference in blocks:
                continue
            span = rows_of[cell.reference]
            blocks[cell.reference] = Block(
                reference=cell.reference,
                row=row.grid_row,
                row_span=span,
                col=cell.hour - OPEN_HOUR + FIRST_COL,
                col_span=cell.colspan,
                state=cell.block_state,
                name=cell.text,
                sub=cell.sub,
                # Over both halves it is the court's, not the first half's.
                label=cell.label if span == 1 else court.name + cell.label.removeprefix(row.label),
            )
    return list(blocks.values())


def _empty_cells(rows: list[Row]) -> list[EmptyCell]:
    return [
        EmptyCell(
            row=row.grid_row,
            col=cell.hour - OPEN_HOUR + FIRST_COL,
            court_code=row.court_code,
            space=row.space,
            hour=cell.hour,
            past=cell.past,
            addable=cell.addable,
            label=cell.label,
        )
        for row in rows
        for cell in row.cells
        if cell.state == FREE
    ]


def build_grid(day: date, *, role: Role | None, now: datetime | None = None) -> Grid:
    """The day's schedule grid for `role`. `now` is injectable so tests can pin the clock."""
    now = now or timezone.now()
    taken = occupancy(day, now=now)
    addable_day = can_add_on(role, day, now)
    groups, rows, blocks = [], [], []
    grid_row = 2  # Row 1 is the hour header.
    kind = None
    for court in Court.objects.filter(is_active=True).order_by("sort_order"):
        if court.kind != kind:  # A heading row before each kind of court.
            kind = court.kind
            groups.append(Group(label=GROUP_LABELS[kind], row=grid_row))
            grid_row += 1
        court_rows = []
        for space in SPACES[court.kind]:  # Basketball: A and B; the rest: F.
            court_rows.append(
                _row(
                    court,
                    space,
                    taken,
                    role=role,
                    day=day,
                    now=now,
                    addable_day=addable_day,
                    grid_row=grid_row,
                )
            )
            grid_row += 1
        rows.extend(court_rows)
        blocks.extend(_blocks(court, court_rows))
    first, last = browse_bounds(now)
    today = local_today(now)
    local = now.astimezone(TIME_ZONE)
    marker = day == today and OPEN_HOUR <= local.hour < CLOSE_HOUR
    now_col = local.hour - OPEN_HOUR + FIRST_COL if marker else None
    return Grid(
        day=day,
        today=today,
        hour_heads=tuple(
            HourHead(
                label=hour_label(hour),
                col=hour - OPEN_HOUR + FIRST_COL,
                past=_hour_ended(day, hour, now),
                current=hour - OPEN_HOUR + FIRST_COL == now_col,
            )
            for hour in range(OPEN_HOUR, CLOSE_HOUR)
        ),
        groups=tuple(groups),
        rows=tuple(rows),
        blocks=tuple(blocks),
        empty_cells=tuple(_empty_cells(rows)),
        now_col=now_col,
        now_minute_class=f"now-m-{local.minute // 5 * 5}" if marker else "",
        now_label=f"{local.hour % 12 or 12}:{local.minute:02d}" if marker else "",
        prev_day=day - timedelta(days=1) if day > first else None,
        next_day=day + timedelta(days=1) if day < last else None,
        min_day=first,
        max_day=last,
    )


def get_booking(reference: str) -> Booking | None:
    """The booking with `reference`, for a permission check and a write through `bookings.holds`."""
    if "\x00" in reference:  # Postgres refuses a NUL in a string, so it is a miss, not a 500.
        return None
    return Booking.objects.select_related("court").filter(reference=reference).first()


def viewer_live_bookings(user, now: datetime) -> int:
    """How many confirmed demo bookings `user` made that haven't ended yet: the demo viewer's
    quota. A count, not a slot check: slots are only ever claimed through `bookings.holds`."""
    return Booking.objects.filter(
        created_by=user, is_demo=True, status=Status.CONFIRMED, ends_at__gt=now
    ).count()


def _clock(moment: datetime) -> str:
    return moment.astimezone(TIME_ZONE).strftime("%I:%M %p").lstrip("0")


def booking_detail(
    booking: Booking, *, role: Role | None, now: datetime | None = None
) -> BookingDetail:
    """The side panel's view of `booking`, masked for `role`. `now` is injectable so tests can
    pin the clock."""
    now = now or timezone.now()
    raw = can_see_personal_data(role)
    start = booking.starts_at.astimezone(TIME_ZONE)
    # A walk-in's note is free text a staff member typed, so only the owner sees it; a block's
    # note is its reason (maintenance, an event) and is shown to everyone.
    show_note = booking.source == Source.BLOCK or raw
    cancellable = can_cancel(role, booking, now=now)
    key = status_key(booking, now)
    return BookingDetail(
        reference=booking.reference,
        court=booking.court.name,
        coverage=f"Half {booking.half}" if booking.half else "Full court",
        sport=Sport(booking.sport).label if booking.sport else "",
        when=f"{start:%a} {start.day} {start:%b}, {_clock(booking.starts_at)} - "
        f"{_clock(booking.ends_at)}",
        source=SOURCE_LABELS[booking.source],
        status=STATUS_LABELS[key],
        is_demo=booking.is_demo,
        name=name_for(role, booking.customer_name),
        email=(booking.customer_email or "") if raw else mask_email(booking.customer_email),
        mobile=(booking.customer_mobile or "") if raw else mask_mobile(booking.customer_mobile),
        price=peso(booking.price_centavos),
        payment_method=booking.payment_method,
        note=booking.note if show_note else "",
        can_cancel=cancellable,
        refund_note=cancellable and role == Role.OWNER and refunds_on_cancel(booking),
        can_check_in=can_check_in(role, booking, now=now),
        status_key=key,
        checked_in_clock=_checked_in_clock(booking),
    )

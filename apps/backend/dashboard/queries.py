"""Everything the staff dashboard reads, and the only place it is read from.

Views and templates never touch the ORM and never mask: every function here takes the viewer's
`Role` and returns rows whose personal fields are already masked for the viewer (RA 10173). The
owner sees them raw. Money stays in centavos; the dataclasses format it with `peso()`.

What counts, by one rule everywhere: a booking is "sold" when it is confirmed and online or
walk-in. Blocks are not bookings: they only shrink the capacity that utilization divides by.
Pending, expired, cancelled and needs_refund bookings hold no lock and earn nothing here. Walk-ins
are cash, so their fee is 0 and their net is their price.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from django.db.models import Count, IntegerField, Q, Sum
from django.db.models.functions import Coalesce, ExtractHour, ExtractIsoWeekDay
from django.utils import timezone

from accounts.roles import Role, can_cancel, can_check_in, can_see_personal_data
from bookings.holds import refunds_on_cancel
from bookings.models import Booking, SlotLock
from bookings.rules import (
    CLOSE_HOUR,
    COURT_COUNTS,
    HOLD_MINUTES,
    OPEN_HOUR,
    SPACES,
    TIME_ZONE,
    Source,
    Sport,
    Status,
    local_today,
)

MASK = "•••"
HOURS_PER_DAY = CLOSE_HOUR - OPEN_HOUR
# Lockable spaces in the venue: 2 basketball courts x (A, B) + 4 tennis + 12 badminton/pickleball.
SPACE_COUNT = sum(count * len(SPACES[kind]) for kind, count in COURT_COUNTS.items())
HEATMAP_DAYS = 28  # Whole weeks, so each weekday appears exactly 4 times.
UPCOMING_HOURS = 3
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
SOURCE_LABELS = {Source.ONLINE: "Online", Source.WALK_IN: "Walk-in", Source.BLOCK: "Block"}

_SOLD = Q(status=Status.CONFIRMED, source__in=[Source.ONLINE, Source.WALK_IN])
_INT = IntegerField()


def peso(centavos: int) -> str:
    """`123456` -> `₱1,235` (whole pesos, rounded half up)."""
    sign = "-" if centavos < 0 else ""
    return f"{sign}₱{(abs(centavos) + 50) // 100:,}"


def mask_email(email: str | None) -> str:
    """`juan.cruz@example.com` -> `j•••@example.com`."""
    if not email:
        return ""
    local, at, domain = email.partition("@")
    if not at or not local:
        return MASK
    return f"{local[0]}{MASK}@{domain}"


def mask_mobile(mobile: str | None) -> str:
    """`+639171234567` -> `•••67` (the last two digits)."""
    digits = "".join(ch for ch in (mobile or "") if ch.isdigit())
    if not digits:
        return ""
    return f"{MASK}{digits[-2:]}" if len(digits) > 2 else MASK


def mask_name(name: str | None) -> str:
    """`Juan Dela Cruz` -> `Juan D.` (first name and the next word's initial). A single word keeps
    only its first letter."""
    parts = (name or "").split()
    if not parts:
        return ""
    if len(parts) == 1:
        return f"{parts[0][0]}{MASK}"
    return f"{parts[0]} {parts[1][0]}."


def name_for(role: Role | None, name: str | None) -> str:
    """A customer name as `role` may see it."""
    return (name or "") if can_see_personal_data(role) else mask_name(name)


@dataclass(frozen=True)
class Revenue:
    gross: int
    fees: int
    net: int

    @property
    def gross_display(self) -> str:
        return peso(self.gross)

    @property
    def fees_display(self) -> str:
        return peso(self.fees)

    @property
    def net_display(self) -> str:
        return peso(self.net)


@dataclass(frozen=True)
class Today:
    bookings: int
    revenue: int
    booked_space_hours: int
    capacity_space_hours: int  # Open space-hours minus those a block takes out.

    @property
    def revenue_display(self) -> str:
        return peso(self.revenue)

    @property
    def utilization_pct(self) -> float:
        if self.capacity_space_hours <= 0:
            return 0.0
        return round(100 * self.booked_space_hours / self.capacity_space_hours, 1)


@dataclass(frozen=True)
class SportRevenue:
    sport: str
    label: str
    bookings: int
    gross: int
    width: int  # 0-100 in steps of 5, relative to the best sport: the CSS class `w-<width>`.

    @property
    def gross_display(self) -> str:
        return peso(self.gross)


@dataclass(frozen=True)
class HeatCell:
    pct: int  # 0-100
    level: int  # 0-5: the CSS class `heat-<level>`.


@dataclass(frozen=True)
class HeatRow:
    label: str
    cells: tuple[HeatCell, ...]


@dataclass(frozen=True)
class Heatmap:
    hours: tuple[str, ...]  # Column headers, 07:00-22:00.
    rows: tuple[HeatRow, ...]  # Monday to Sunday.


@dataclass(frozen=True)
class Upcoming:
    court: str
    sport: str
    coverage: str  # "Full court", "Half A" or "Half B".
    when: str  # "3:00 PM - 5:00 PM", prefixed with the day if it isn't today.
    source: str
    name: str  # Masked for the viewer.


@dataclass(frozen=True)
class Alerts:
    needs_refund: int
    active_holds: int

    @property
    def hold_minutes(self) -> int:
        """How long an unpaid online booking holds its slot."""
        return HOLD_MINUTES


@dataclass(frozen=True)
class Overview:
    today: Today
    revenue_7d: Revenue
    revenue_30d: Revenue
    by_sport_30d: tuple[SportRevenue, ...]
    heatmap: Heatmap
    upcoming: tuple[Upcoming, ...]
    alerts: Alerts


def _midnight(day) -> datetime:
    return datetime.combine(day, time(0), tzinfo=TIME_ZONE)


def _lock_counts(start: datetime, end: datetime) -> dict[str, int]:
    """Confirmed space-hours starting in [start, end), by booking source."""
    rows = (
        SlotLock.objects.filter(
            booking__status=Status.CONFIRMED, starts_at__gte=start, starts_at__lt=end
        )
        .values("booking__source")
        .annotate(n=Count("id"))
        .order_by()
    )
    return {row["booking__source"]: row["n"] for row in rows}


def _today(now: datetime) -> Today:
    start = _midnight(local_today(now))
    end = start + timedelta(days=1)
    sold = Booking.objects.filter(_SOLD, starts_at__gte=start, starts_at__lt=end).aggregate(
        bookings=Count("id"), revenue=Coalesce(Sum("price_centavos"), 0)
    )
    locks = _lock_counts(start, end)
    return Today(
        bookings=sold["bookings"],
        revenue=sold["revenue"],
        booked_space_hours=locks.get(Source.ONLINE, 0) + locks.get(Source.WALK_IN, 0),
        capacity_space_hours=SPACE_COUNT * HOURS_PER_DAY - locks.get(Source.BLOCK, 0),
    )


def _revenue(now: datetime, days: int) -> Revenue:
    totals = (
        Booking.objects.filter(_SOLD, starts_at__gte=now - timedelta(days=days))
        .filter(starts_at__lte=now)
        .aggregate(
            gross=Coalesce(Sum("price_centavos"), 0),
            fees=Coalesce(Sum(Coalesce("fee_centavos", 0, output_field=_INT)), 0),
            net=Coalesce(Sum(Coalesce("net_centavos", "price_centavos", output_field=_INT)), 0),
        )
    )
    return Revenue(**totals)


def _by_sport(now: datetime, days: int) -> tuple[SportRevenue, ...]:
    rows = list(
        Booking.objects.filter(_SOLD, starts_at__gte=now - timedelta(days=days), starts_at__lte=now)
        .values("sport")
        .annotate(bookings=Count("id"), gross=Sum("price_centavos"))
        .order_by("-gross", "sport")
    )
    best = max((row["gross"] for row in rows), default=0)
    result = []
    for row in rows:
        # A sport that earned anything gets a visible bar (at least 5).
        width = max(5, 5 * round(20 * row["gross"] / best)) if row["gross"] else 0
        result.append(
            SportRevenue(
                sport=row["sport"],
                label=Sport(row["sport"]).label,
                bookings=row["bookings"],
                gross=row["gross"],
                width=width,
            )
        )
    return tuple(result)


def _heatmap(now: datetime) -> Heatmap:
    """Utilization by weekday x hour over the last 28 whole days (today excluded): booked
    space-hours over the capacity left after blocks, as an integer percentage."""
    end = _midnight(local_today(now))
    start = end - timedelta(days=HEATMAP_DAYS)
    rows = (
        SlotLock.objects.filter(
            booking__status=Status.CONFIRMED, starts_at__gte=start, starts_at__lt=end
        )
        .annotate(
            weekday=ExtractIsoWeekDay("starts_at", tzinfo=TIME_ZONE),
            hour=ExtractHour("starts_at", tzinfo=TIME_ZONE),
        )
        .values("weekday", "hour", "booking__source")
        .annotate(n=Count("id"))
        .order_by()
    )
    booked: dict[tuple[int, int], int] = {}
    blocked: dict[tuple[int, int], int] = {}
    for row in rows:
        bucket = blocked if row["booking__source"] == Source.BLOCK else booked
        key = (row["weekday"], row["hour"])
        bucket[key] = bucket.get(key, 0) + row["n"]

    days_per_weekday = HEATMAP_DAYS // 7
    table = []
    for weekday, label in enumerate(WEEKDAYS, start=1):
        cells = []
        for hour in range(OPEN_HOUR, CLOSE_HOUR):
            key = (weekday, hour)
            capacity = SPACE_COUNT * days_per_weekday - blocked.get(key, 0)
            pct = min(100, round(100 * booked.get(key, 0) / capacity)) if capacity > 0 else 0
            cells.append(HeatCell(pct=pct, level=-(-pct // 20)))  # ceil(pct / 20): 0, 1..5.
        table.append(HeatRow(label=label, cells=tuple(cells)))
    hours = tuple(f"{hour:02d}" for hour in range(OPEN_HOUR, CLOSE_HOUR))
    return Heatmap(hours=hours, rows=tuple(table))


def _clock(moment: datetime) -> str:
    return moment.astimezone(TIME_ZONE).strftime("%I:%M %p").lstrip("0")


def _upcoming(role: Role | None, now: datetime) -> tuple[Upcoming, ...]:
    today = local_today(now)
    bookings = (
        Booking.objects.select_related("court")
        .filter(_SOLD, starts_at__gte=now, starts_at__lt=now + timedelta(hours=UPCOMING_HOURS))
        .order_by("starts_at", "court__sort_order")
    )
    result = []
    for booking in bookings:
        start = booking.starts_at.astimezone(TIME_ZONE)
        day = "" if start.date() == today else f"{start:%a} "
        result.append(
            Upcoming(
                court=booking.court.name,
                sport=Sport(booking.sport).label,
                coverage=f"Half {booking.half}" if booking.half else "Full court",
                when=f"{day}{_clock(booking.starts_at)} - {_clock(booking.ends_at)}",
                source=SOURCE_LABELS[booking.source],
                name=name_for(role, booking.customer_name),
            )
        )
    return tuple(result)


def _alerts(now: datetime) -> Alerts:
    counts = Booking.objects.aggregate(
        needs_refund=Count("id", filter=Q(status=Status.NEEDS_REFUND)),
        active_holds=Count("id", filter=Q(status=Status.PENDING, hold_expires_at__gt=now)),
    )
    return Alerts(**counts)


def overview(*, role: Role | None, now: datetime | None = None) -> Overview:
    """The overview page's data, masked for `role`. `now` is injectable so tests can pin the day."""
    now = now or timezone.now()
    return Overview(
        today=_today(now),
        revenue_7d=_revenue(now, 7),
        revenue_30d=_revenue(now, 30),
        by_sport_30d=_by_sport(now, 30),
        heatmap=_heatmap(now),
        upcoming=_upcoming(role, now),
        alerts=_alerts(now),
    )


# --- The bookings list and a booking's detail ----------------------------------------------------

PAGE_SIZE = 25
MAX_QUERY_LENGTH = 60
DEFAULT_SORT = "-starts_at"
SORTS = {
    "-starts_at": "Start time, latest first",
    "starts_at": "Start time, earliest first",
    "-created_at": "Newest booked",
    "-price_centavos": "Price, highest first",
}
# Two derived statuses (see `status_key`) join the stored ones as extra filters; `confirmed` still
# lists every confirmed booking, ended or checked in or not.
CHECKED_IN = "checked_in"
COMPLETED = "completed"
STATUS_CHOICES = (*Status.choices, (CHECKED_IN, "Checked in"), (COMPLETED, "Completed"))
SPORT_CHOICES = tuple(Sport.choices)
SOURCE_CHOICES = tuple((source.value, SOURCE_LABELS[source]) for source in Source)
# Dates outside this range are treated as invalid, so `date_to + 1 day` can never overflow.
_FIRST_DATE = date(2000, 1, 1)
_LAST_DATE = date(2100, 12, 31)


@dataclass(frozen=True)
class ListParams:
    """The bookings list's state, as it lives in the URL. Every field is already validated."""

    q: str
    status: str | None
    sport: str | None
    source: str | None
    date_from: date | None
    date_to: date | None
    sort: str
    page: int

    def query_string(self, page: int | None = None) -> str:
        """The URL query for these params (defaults left out), optionally at another page."""
        page = self.page if page is None else page
        pairs = {
            "q": self.q,
            "status": self.status,
            "sport": self.sport,
            "source": self.source,
            "from": self.date_from.isoformat() if self.date_from else None,
            "to": self.date_to.isoformat() if self.date_to else None,
            "sort": self.sort if self.sort != DEFAULT_SORT else None,
            "page": page if page > 1 else None,
        }
        return urlencode({key: value for key, value in pairs.items() if value})


def _choice(value: str | None, allowed) -> str | None:
    return value if value in allowed else None


def _date(value: str | None) -> date | None:
    try:
        parsed = date.fromisoformat(value or "")
    except ValueError:
        return None
    return parsed if _FIRST_DATE <= parsed <= _LAST_DATE else None


def _page_number(value: str | None) -> int:
    try:
        return max(1, int(value or "1"))
    except ValueError:
        return 1


def parse_list_params(querydict) -> ListParams:
    """Read the list's URL parameters defensively: anything invalid falls back to its default."""
    get = querydict.get
    sort = get("sort")
    return ListParams(
        # Postgres refuses a NUL in a string, so it is dropped rather than left to raise.
        q=(get("q") or "").replace("\x00", "").strip()[:MAX_QUERY_LENGTH],
        status=_choice(get("status"), dict(STATUS_CHOICES)),
        sport=_choice(get("sport"), Sport.values),
        source=_choice(get("source"), Source.values),
        date_from=_date(get("from")),
        date_to=_date(get("to")),
        sort=sort if sort in SORTS else DEFAULT_SORT,
        page=_page_number(get("page")),
    )


@dataclass(frozen=True)
class BookingRow:
    reference: str
    court: str
    sport: str  # Label; empty for a block.
    when: str
    source: str  # "online", "walk_in" or "block".
    source_label: str
    status: str  # The value, for the badge's CSS class.
    status_label: str
    status_key: str  # See `status_key`.
    checked_in_clock: str  # "6:55 PM", or empty.
    is_demo: bool
    name: str  # The personal fields are masked for the viewer.
    email: str
    mobile: str
    price: str  # Empty for a block.


@dataclass(frozen=True)
class Page:
    rows: tuple[BookingRow, ...]
    total: int
    page: int  # The page actually shown (the requested one, kept within range).
    pages: int
    params: ListParams

    @property
    def first(self) -> int:
        return (self.page - 1) * PAGE_SIZE + 1 if self.total else 0

    @property
    def last(self) -> int:
        return self.first + len(self.rows) - 1 if self.total else 0

    @property
    def query(self) -> str:
        return self.params.query_string(self.page)

    @property
    def prev_query(self) -> str | None:
        return self.params.query_string(self.page - 1) if self.page > 1 else None

    @property
    def next_query(self) -> str | None:
        return self.params.query_string(self.page + 1) if self.page < self.pages else None

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages


@dataclass(frozen=True)
class BookingDetail:
    reference: str
    court: str
    coverage: str  # "Full court", "Half A" or "Half B".
    sport: str
    when: str
    hours: int
    source: str
    source_label: str
    status: str
    status_label: str
    status_key: str  # See `status_key`.
    checked_in_clock: str  # "6:55 PM", or empty.
    is_demo: bool
    name: str  # The personal fields are masked for the viewer.
    email: str
    mobile: str
    note: str
    price: str
    payment_method: str
    fee: str  # Empty when none was charged.
    net: str
    paid_at: str
    consent_at: str
    created_at: str
    cancelled_at: str
    anonymized: bool
    can_cancel: bool
    can_check_in: bool
    refund_note: bool  # The owner cancelling a paid online booking refunds it in PayMongo.

    @property
    def needs_refund(self) -> bool:
        return self.status == Status.NEEDS_REFUND


def status_key(booking: Booking, now: datetime) -> str:
    """The status staff see, and the only place it is decided: `block` for a block; for a
    confirmed booking, `completed` once it has ended, else `checked_in` once checked in; otherwise
    the stored status."""
    if booking.source == Source.BLOCK:
        return "block"
    if booking.status == Status.CONFIRMED:
        if booking.ends_at <= now:
            return COMPLETED
        if booking.checked_in_at is not None:
            return CHECKED_IN
    return booking.status


def _status_filter(status: str, now: datetime) -> Q:
    """The list's status filter. The derived ones match `status_key`."""
    if status == CHECKED_IN:
        return Q(status=Status.CONFIRMED, checked_in_at__isnull=False, ends_at__gt=now) & ~Q(
            source=Source.BLOCK
        )
    if status == COMPLETED:
        return Q(status=Status.CONFIRMED, ends_at__lte=now) & ~Q(source=Source.BLOCK)
    return Q(status=status)


def _checked_in_clock(booking: Booking) -> str:
    return _clock(booking.checked_in_at) if booking.checked_in_at else ""


def _stamp(moment: datetime | None) -> str:
    """`2 Nov 2026, 2:00 PM` in venue time, or empty."""
    if moment is None:
        return ""
    local = moment.astimezone(TIME_ZONE)
    return f"{local.day} {local:%b %Y}, {_clock(moment)}"


def _when(booking: Booking) -> str:
    start = booking.starts_at.astimezone(TIME_ZONE)
    return (
        f"{start:%a} {start.day} {start:%b %Y}, "
        f"{_clock(booking.starts_at)} - {_clock(booking.ends_at)}"
    )


def _personal(role: Role | None, booking: Booking) -> tuple[str, str, str]:
    """Name, email and mobile as `role` may see them."""
    if can_see_personal_data(role):
        return (
            booking.customer_name or "",
            booking.customer_email or "",
            booking.customer_mobile or "",
        )
    return (
        mask_name(booking.customer_name),
        mask_email(booking.customer_email),
        mask_mobile(booking.customer_mobile),
    )


def _row(role: Role | None, booking: Booking, now: datetime) -> BookingRow:
    name, email, mobile = _personal(role, booking)
    return BookingRow(
        reference=booking.reference,
        court=booking.court.name + (f" · Half {booking.half}" if booking.half else ""),
        sport=Sport(booking.sport).label if booking.sport else "",
        when=_when(booking),
        source=booking.source,
        source_label=SOURCE_LABELS[booking.source],
        status=booking.status,
        status_label=Status(booking.status).label,
        status_key=status_key(booking, now),
        checked_in_clock=_checked_in_clock(booking),
        is_demo=booking.is_demo,
        name=name,
        email=email,
        mobile=mobile,
        price="" if booking.source == Source.BLOCK else peso(booking.price_centavos),
    )


def _search(role: Role | None, text: str) -> Q:
    """What a search term matches. The owner searches reference, name, email and mobile. A role
    that can't see personal data searches references, and names on demo bookings only, so the
    public viewer can never use it to confirm that a name, email or mobile number belongs to a
    real customer."""
    if can_see_personal_data(role):
        return (
            Q(reference__icontains=text)
            | Q(customer_name__icontains=text)
            | Q(customer_email__icontains=text)
            | Q(customer_mobile__icontains=text)
        )
    return Q(reference__icontains=text) | Q(customer_name__icontains=text, is_demo=True)


def list_bookings(*, role: Role | None, params: ListParams, now: datetime | None = None) -> Page:
    """One page of bookings (25), filtered and sorted by `params`, masked for `role`. `now` is
    injectable so tests can pin the clock."""
    now = now or timezone.now()
    bookings = Booking.objects.select_related("court")
    if params.q:
        bookings = bookings.filter(_search(role, params.q))
    if params.status:
        bookings = bookings.filter(_status_filter(params.status, now))
    if params.sport:
        bookings = bookings.filter(sport=params.sport)
    if params.source:
        bookings = bookings.filter(source=params.source)
    if params.date_from:
        bookings = bookings.filter(starts_at__gte=_midnight(params.date_from))
    if params.date_to:
        bookings = bookings.filter(starts_at__lt=_midnight(params.date_to + timedelta(days=1)))
    total = bookings.count()
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(params.page, pages)
    offset = (page - 1) * PAGE_SIZE
    # `reference` breaks ties so a page boundary never repeats or skips a row.
    rows = bookings.order_by(params.sort, "reference")[offset : offset + PAGE_SIZE]
    return Page(
        rows=tuple(_row(role, booking, now) for booking in rows),
        total=total,
        page=page,
        pages=pages,
        params=replace(params, page=page),
    )


def get_booking(
    *, role: Role | None, reference: str, now: datetime | None = None
) -> BookingDetail | None:
    """A booking's full detail, masked for `role`; None when the reference is unknown. `now` is
    injectable so tests can pin the clock."""
    if "\x00" in reference:  # Postgres refuses a NUL in a string, so it is a miss, not a 500.
        return None
    now = now or timezone.now()
    booking = Booking.objects.select_related("court").filter(reference=reference).first()
    if booking is None:
        return None
    name, email, mobile = _personal(role, booking)
    # A walk-in's note is free text a staff member typed, so only the owner sees it; a block's
    # note is its reason (maintenance, an event) and is shown to everyone.
    show_note = booking.source == Source.BLOCK or can_see_personal_data(role)
    cancellable = can_cancel(role, booking, now=now)
    return BookingDetail(
        reference=booking.reference,
        court=booking.court.name,
        coverage=f"Half {booking.half}" if booking.half else "Full court",
        sport=Sport(booking.sport).label if booking.sport else "",
        when=_when(booking),
        hours=booking.hours,
        source=booking.source,
        source_label=SOURCE_LABELS[booking.source],
        status=booking.status,
        status_label=Status(booking.status).label,
        status_key=status_key(booking, now),
        checked_in_clock=_checked_in_clock(booking),
        is_demo=booking.is_demo,
        name=name,
        email=email,
        mobile=mobile,
        note=booking.note if show_note else "",
        price=peso(booking.price_centavos),
        payment_method=booking.payment_method,
        fee=peso(booking.fee_centavos) if booking.fee_centavos is not None else "",
        net=peso(booking.net_centavos) if booking.net_centavos is not None else "",
        paid_at=_stamp(booking.paid_at),
        consent_at=_stamp(booking.consent_at),
        created_at=_stamp(booking.created_at),
        cancelled_at=_stamp(booking.cancelled_at),
        anonymized=booking.anonymized_at is not None,
        can_cancel=cancellable,
        can_check_in=can_check_in(role, booking, now=now),
        refund_note=cancellable and role == Role.OWNER and refunds_on_cancel(booking),
    )

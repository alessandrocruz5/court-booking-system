"""Everything the staff dashboard reads, and the only place it is read from.

Views and templates never touch the ORM and never mask: every function here takes the viewer's
`Role` and returns rows whose personal fields are already masked for the viewer (RA 10173). The
owner sees them raw. Money stays in centavos; the dataclasses format it with `peso()`.

What counts, by one rule everywhere: a booking is "sold" when it is confirmed and online or
walk-in. Blocks are not bookings: they only shrink the capacity that utilization divides by.
Pending, expired, cancelled and needs_refund bookings hold no lock and earn nothing here. Walk-ins
are cash, so their fee is 0 and their net is their price.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.db.models import Count, IntegerField, Q, Sum
from django.db.models.functions import Coalesce, ExtractHour, ExtractIsoWeekDay
from django.utils import timezone

from accounts.roles import Role, can_see_personal_data
from bookings.models import Booking, SlotLock
from bookings.rules import (
    CLOSE_HOUR,
    COURT_COUNTS,
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

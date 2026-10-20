"""Booking rules for Kalaro Courts: constants and pure validation (no database access).

`COURT_COUNTS` must match the courts seeded by migration `0002_courts` (tested). The catalog API
reads these constants, so it never queries the database.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from django.db.models import TextChoices

if TYPE_CHECKING:
    from bookings.models import Court

TIME_ZONE = ZoneInfo("Asia/Manila")
OPEN_HOUR = 7
CLOSE_HOUR = 23
WINDOW_DAYS = 7
MAX_HOURS = 3
HOLD_MINUTES = 20


class CourtKind(TextChoices):
    BASKETBALL = "basketball"
    TENNIS = "tennis"
    MULTI = "multi"


class Sport(TextChoices):
    BASKETBALL = "basketball"
    VOLLEYBALL = "volleyball"
    TENNIS = "tennis"
    BADMINTON = "badminton"
    PICKLEBALL = "pickleball"


class Coverage(TextChoices):
    FULL = "full"
    HALF = "half"


class Half(TextChoices):
    A = "A"
    B = "B"


class Source(TextChoices):
    ONLINE = "online"
    WALK_IN = "walk_in"
    BLOCK = "block"


class Status(TextChoices):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    NEEDS_REFUND = "needs_refund"


@dataclass(frozen=True)
class SportRule:
    court_kind: str
    coverages: tuple[str, ...]


SPORTS: dict[str, SportRule] = {
    Sport.BASKETBALL: SportRule(CourtKind.BASKETBALL, (Coverage.FULL, Coverage.HALF)),
    Sport.VOLLEYBALL: SportRule(CourtKind.BASKETBALL, (Coverage.FULL,)),
    Sport.TENNIS: SportRule(CourtKind.TENNIS, (Coverage.FULL,)),
    Sport.BADMINTON: SportRule(CourtKind.MULTI, (Coverage.FULL,)),
    Sport.PICKLEBALL: SportRule(CourtKind.MULTI, (Coverage.FULL,)),
}

# Lockable spaces per court kind. A full basketball booking takes both A and B; "F" is the whole
# court for kinds that are never split.
SPACES: dict[str, tuple[str, ...]] = {
    CourtKind.BASKETBALL: ("A", "B"),
    CourtKind.TENNIS: ("F",),
    CourtKind.MULTI: ("F",),
}

COURT_COUNTS: dict[str, int] = {
    CourtKind.BASKETBALL: 2,
    CourtKind.TENNIS: 4,
    CourtKind.MULTI: 12,
}

STAFF_WINDOW_DAYS = 30


class BookingRuleError(Exception):
    """A request that breaks a booking rule. `code` is a stable, user-safe identifier."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def local_today(now: datetime) -> date:
    return now.astimezone(TIME_ZONE).date()


def bookable_dates(now: datetime) -> list[date]:
    today = local_today(now)
    return [today + timedelta(days=n) for n in range(WINDOW_DAYS)]


def slot_starts(day: date, start_hour: int, hours: int) -> list[datetime]:
    first = datetime.combine(day, time(start_hour), tzinfo=TIME_ZONE)
    return [first + timedelta(hours=n) for n in range(hours)]


def spaces_for(court: Court, coverage: str, half: str | None) -> list[str]:
    if court.kind == CourtKind.BASKETBALL and coverage == Coverage.HALF:
        if half not in (Half.A, Half.B):
            raise ValueError("half coverage needs half A or B")
        return [str(half)]
    return list(SPACES[court.kind])


def _check_sport(sport: str, coverage: str) -> SportRule:
    rule = SPORTS.get(sport)
    if rule is None:
        raise BookingRuleError("unknown_sport")
    if coverage not in rule.coverages:
        raise BookingRuleError("coverage_not_allowed")
    return rule


def _check_court(court: Court, rule: SportRule | None) -> None:
    if not court.is_active:
        raise BookingRuleError("court_inactive")
    if rule is not None and court.kind != rule.court_kind:
        raise BookingRuleError("wrong_court_for_sport")


def _check_hours(hours: int) -> None:
    if isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= MAX_HOURS:
        raise BookingRuleError("invalid_hours")


def _check_span(start_hour: int, hours: int) -> None:
    if (
        isinstance(start_hour, bool)
        or not isinstance(start_hour, int)
        or start_hour < OPEN_HOUR
        or start_hour + hours > CLOSE_HOUR
    ):
        raise BookingRuleError("outside_hours")


def validate_search(*, sport: str, coverage: str, day: date, hours: int, now: datetime) -> None:
    """The court-independent rules for an availability search."""
    _check_sport(sport, coverage)
    _check_hours(hours)
    if day not in bookable_dates(now):
        raise BookingRuleError("outside_window")


def validate_customer_request(
    *,
    court: Court,
    sport: str,
    coverage: str,
    day: date,
    start_hour: int,
    hours: int,
    now: datetime,
) -> None:
    rule = SPORTS.get(sport)
    if rule is None:
        raise BookingRuleError("unknown_sport")
    _check_court(court, rule)
    _check_sport(sport, coverage)
    _check_hours(hours)
    _check_span(start_hour, hours)
    if day not in bookable_dates(now):
        raise BookingRuleError("outside_window")
    if slot_starts(day, start_hour, 1)[0] <= now:
        raise BookingRuleError("in_the_past")


def validate_staff_request(
    *,
    court: Court,
    sport: str | None,
    coverage: str,
    day: date,
    start_hour: int,
    hours: int,
    now: datetime,
) -> None:
    """Staff rules: `sport=None` is a block. The window is today..today+30, and the booking only
    has to end after `now`, so a walk-in can be logged for the hour in progress."""
    rule = None
    if sport is not None:
        rule = SPORTS.get(sport)
        if rule is None:
            raise BookingRuleError("unknown_sport")
    _check_court(court, rule)
    if sport is not None:
        _check_sport(sport, coverage)
    _check_hours(hours)
    _check_span(start_hour, hours)
    today = local_today(now)
    if not today <= day <= today + timedelta(days=STAFF_WINDOW_DAYS):
        raise BookingRuleError("outside_window")
    if slot_starts(day, start_hour, hours)[-1] + timedelta(hours=1) <= now:
        raise BookingRuleError("in_the_past")

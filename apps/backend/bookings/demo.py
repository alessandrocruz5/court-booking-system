"""Deterministic demo bookings, so the venue looks busy on any day someone opens the demo.

`generate` deletes every `is_demo` booking, plans a fresh set from today - 30 to today + 6 in
memory (a pure function of `today`, the courts and `rng`), then claims each one through
`claim_slots` in its own transaction. The plan only keeps demo bookings from overlapping each
other; the `SlotLock` constraint still decides every slot, so a demo booking that clashes with a
real one is skipped and the real booking wins. Non-demo bookings are never read, changed or
deleted here.

Demo rows carry the markers the dashboard and the anonymizer rely on: `is_demo`, `@example.com`
emails and `+63900000xxxx` mobiles. Logs carry counts only.
"""

import logging
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.db import IntegrityError, transaction

from bookings import pricing, rules
from bookings.holds import SlotTaken, claim_slots
from bookings.models import Booking, Court
from bookings.references import new_reference
from bookings.rules import (
    CLOSE_HOUR,
    OPEN_HOUR,
    SPACES,
    CourtKind,
    Coverage,
    Source,
    Sport,
    Status,
)

logger = logging.getLogger("cb.demo")

DAYS_BACK = 30
DAYS_AHEAD = 6

# Occupancy per hour band: 07-09, 09-17 and 17-23. Weekends x1.25, capped.
WEEKEND_FACTOR = 1.25
MAX_RATE = 0.9
KIND_FACTOR = {
    # Multi courts are the busiest; tennis peaks in mornings and evenings.
    CourtKind.MULTI: {"morning": 1.15, "day": 1.15, "evening": 1.15},
    CourtKind.TENNIS: {"morning": 1.4, "day": 0.6, "evening": 1.0},
    CourtKind.BASKETBALL: {"morning": 0.9, "day": 1.0, "evening": 0.9},
}
BASE_RATE = {"morning": 0.35, "day": 0.2, "evening": 0.75}

DURATIONS = (1, 2, 3)
DURATION_WEIGHTS = (50, 40, 10)
MEAN_DURATION = sum(h * w for h, w in zip(DURATIONS, DURATION_WEIGHTS, strict=True)) / 100

ONLINE_SHARE = 0.8
BASKETBALL_HALF_SHARE = 0.30
VOLLEYBALL_SHARE = 0.15
BADMINTON_SHARE = 0.6

PAYMENT_METHODS = ("gcash", "card", "paymaya", "grab_pay")
PAYMENT_WEIGHTS = (55, 25, 15, 5)
# Illustrative demo rates only, NOT PayMongo's actual pricing: (basis points, fixed centavos).
DEMO_FEE_RATES: dict[str, tuple[int, int]] = {
    "gcash": (250, 0),
    "paymaya": (200, 0),
    "grab_pay": (220, 0),
    "card": (350, 1_500),
}

# (note, possible start hours, hours). One or two blocks a week, on random courts.
BLOCKS = (
    ("Resurfacing", (7, 8, 9), 3),
    ("League night", (18, 19, 20), 3),
    ("Coaching clinic", (8, 9, 10, 14), 2),
    ("Maintenance", (9, 10, 13), 2),
)

FIRST_NAMES = (
    "Juan", "Jose", "Maria", "Ana", "Mark", "John", "Michael", "Angelo", "Carlo", "Paolo",
    "Miguel", "Rafael", "Gabriel", "Joshua", "Christian", "Kristine", "Angelica", "Camille",
    "Patricia", "Nicole", "Bea", "Jasmine", "Erika", "Mae", "Grace", "Joy", "Liza", "Rhea",
    "Ramon", "Dennis",
)  # fmt: skip
LAST_NAMES = (
    "Santos", "Reyes", "Cruz", "Bautista", "Garcia", "Mendoza", "Torres", "Tomas", "Andrada",
    "Castillo", "Flores", "Villanueva", "Ramos", "Aquino", "Navarro", "Dela Cruz", "Gonzales",
    "Lopez", "Rivera", "Fernandez", "Domingo", "Mercado", "Aguilar", "Salazar", "Pascual",
    "Soriano", "Manalo", "Lim", "Tan", "Del Rosario",
)  # fmt: skip


@dataclass(frozen=True)
class Person:
    name: str
    email: str
    mobile: str


@dataclass(frozen=True)
class Planned:
    court: Court
    sport: str | None
    coverage: str
    half: str | None
    day: date
    start_hour: int
    hours: int
    source: str
    note: str
    person: Person | None
    payment_method: str
    payment_hex: str
    created_u: float
    paid_u: float


def _band(hour: int) -> str:
    if hour < 9:
        return "morning"
    if hour < 17:
        return "day"
    return "evening"


def _rate(kind: str, day: date, hour: int) -> float:
    """The share of this court-hour that should be booked."""
    band = _band(hour)
    rate = BASE_RATE[band] * KIND_FACTOR[kind][band]
    if day.weekday() >= 5:
        rate *= WEEKEND_FACTOR
    return min(rate, MAX_RATE)


def _start_probability(rate: float) -> float:
    """The chance a free hour starts a booking, so that, with bookings lasting MEAN_DURATION
    hours on average, about `rate` of the hours end up booked."""
    return rate / (MEAN_DURATION - rate * (MEAN_DURATION - 1))


def _person(rng: random.Random) -> Person:
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    slug = f"{first}.{last}".lower().replace(" ", "")
    return Person(
        name=f"{first} {last}",
        email=f"{slug}.{rng.randrange(100):02d}@example.com",
        mobile=f"+63900000{rng.randrange(10_000):04d}",
    )


def _customer_booking(
    rng: random.Random,
    *,
    court: Court,
    sport: str,
    coverage: str,
    half: str | None,
    day: date,
    start_hour: int,
    hours: int,
) -> Planned:
    online = rng.random() < ONLINE_SHARE
    method = rng.choices(PAYMENT_METHODS, PAYMENT_WEIGHTS)[0] if online else "cash"
    return Planned(
        court=court,
        sport=sport,
        coverage=coverage,
        half=half,
        day=day,
        start_hour=start_hour,
        hours=hours,
        source=Source.ONLINE if online else Source.WALK_IN,
        note="",
        person=_person(rng),
        payment_method=method,
        payment_hex=f"{rng.getrandbits(96):024x}" if online else "",
        created_u=rng.random(),
        paid_u=rng.random(),
    )


def _fits(busy: set[tuple[str, int]], spaces: list[str], start_hour: int, hours: int) -> int:
    """The longest run, up to `hours`, that is free on every space and ends by closing time."""
    fit = 0
    for hour in range(start_hour, min(start_hour + hours, CLOSE_HOUR)):
        if any((space, hour) in busy for space in spaces):
            break
        fit += 1
    return fit


def _occupy(busy: set[tuple[str, int]], spaces: list[str], start_hour: int, hours: int) -> None:
    busy.update((space, hour) for space in spaces for hour in range(start_hour, start_hour + hours))


def plan(*, today: date, courts: list[Court], rng: random.Random) -> list[Planned]:
    """The demo bookings for today - 30 .. today + 6. Uses only `rng`, never the database."""
    days = [today + timedelta(days=n) for n in range(-DAYS_BACK, DAYS_AHEAD + 1)]
    busy: dict[tuple[int, date], set[tuple[str, int]]] = {}
    planned: list[Planned] = []

    for week in range(0, len(days), 7):
        for _ in range(rng.choice((1, 2))):
            day = rng.choice(days[week : week + 7])
            court = rng.choice(courts)
            note, start_hours, hours = rng.choice(BLOCKS)
            start_hour = rng.choice(start_hours)
            spaces = list(SPACES[court.kind])
            taken = busy.setdefault((court.pk, day), set())
            if _fits(taken, spaces, start_hour, hours) < hours:
                continue
            _occupy(taken, spaces, start_hour, hours)
            planned.append(
                Planned(
                    court=court,
                    sport=None,
                    coverage=Coverage.FULL,
                    half=None,
                    day=day,
                    start_hour=start_hour,
                    hours=hours,
                    source=Source.BLOCK,
                    note=note,
                    person=None,
                    payment_method="",
                    payment_hex="",
                    created_u=rng.random(),
                    paid_u=0.0,
                )
            )

    for day in days:
        for court in courts:
            taken = busy.setdefault((court.pk, day), set())
            tracks = SPACES[court.kind]
            for hour in range(OPEN_HOUR, CLOSE_HOUR):
                free = [space for space in tracks if (space, hour) not in taken]
                if not free or rng.random() >= _start_probability(_rate(court.kind, day, hour)):
                    continue
                wanted = rng.choices(DURATIONS, DURATION_WEIGHTS)[0]
                if court.kind == CourtKind.BASKETBALL:
                    roll = rng.random()
                    if len(free) == 1 or roll < BASKETBALL_HALF_SHARE:
                        sport, coverage, half = Sport.BASKETBALL, Coverage.HALF, rng.choice(free)
                    elif roll < BASKETBALL_HALF_SHARE + VOLLEYBALL_SHARE:
                        sport, coverage, half = Sport.VOLLEYBALL, Coverage.FULL, None
                    else:
                        sport, coverage, half = Sport.BASKETBALL, Coverage.FULL, None
                elif court.kind == CourtKind.TENNIS:
                    sport, coverage, half = Sport.TENNIS, Coverage.FULL, None
                else:
                    sport = Sport.BADMINTON if rng.random() < BADMINTON_SHARE else Sport.PICKLEBALL
                    coverage, half = Coverage.FULL, None
                spaces = rules.spaces_for(court, coverage, half)
                hours = _fits(taken, spaces, hour, wanted)
                _occupy(taken, spaces, hour, hours)
                planned.append(
                    _customer_booking(
                        rng,
                        court=court,
                        sport=sport,
                        coverage=coverage,
                        half=half,
                        day=day,
                        start_hour=hour,
                        hours=hours,
                    )
                )
    return planned


def _between(u: float, earliest: datetime, latest: datetime) -> datetime:
    return earliest + (latest - earliest) * u


def _timestamps(p: Planned, starts_at: datetime, now: datetime) -> tuple[datetime, datetime | None]:
    """(created_at, paid_at). Online: paid 1-72 h before the start and before `now` (a booking
    more than 72 h out was paid within the last 72 h), created a few minutes before paying.
    Walk-ins and blocks: created up to 3 days before the start, and before `now`."""
    if p.source == Source.ONLINE:
        latest = min(starts_at - timedelta(hours=1), now - timedelta(minutes=5))
        earliest = starts_at - timedelta(hours=72)
        if earliest >= latest:
            earliest = latest - timedelta(hours=72)
        paid_at = _between(p.paid_u, earliest, latest)
        return paid_at - timedelta(minutes=2 + int(p.created_u * 13)), paid_at
    latest = min(starts_at, now - timedelta(minutes=5))
    return _between(p.created_u, latest - timedelta(days=3), latest), None


def _fields(p: Planned, *, now: datetime) -> tuple[dict, datetime]:
    starts = rules.slot_starts(p.day, p.start_hour, p.hours)
    created_at, paid_at = _timestamps(p, starts[0], now)
    fields = {
        "court": p.court,
        "sport": p.sport,
        "coverage": p.coverage,
        "half": p.half,
        "starts_at": starts[0],
        "ends_at": starts[-1] + timedelta(hours=1),
        "hours": p.hours,
        "source": p.source,
        "status": Status.CONFIRMED,
        "note": p.note,
        "payment_method": p.payment_method,
        "is_demo": True,
    }
    if p.sport is None:
        fields["price_centavos"] = 0
    else:
        fields["price_centavos"] = pricing.quote(p.sport, p.coverage, p.day, p.start_hour, p.hours)
    if p.person is not None:
        fields |= {
            "customer_name": p.person.name,
            "customer_email": p.person.email,
            "customer_mobile": p.person.mobile,
            "consent_at": created_at,
        }
    if p.source == Source.ONLINE:
        bps, fixed = DEMO_FEE_RATES[p.payment_method]
        fee = (fields["price_centavos"] * bps + 5_000) // 10_000 + fixed
        fields |= {
            "payment_id": f"pay_demo_{p.payment_hex}",
            "fee_centavos": fee,
            "net_centavos": fields["price_centavos"] - fee,
            "paid_at": paid_at,
        }
    return fields, created_at


def _is_reference_clash(exc: IntegrityError) -> bool:
    diag = getattr(exc.__cause__, "diag", None)
    return "reference" in (getattr(diag, "constraint_name", None) or "")


def generate(*, today: date, now: datetime, rng: random.Random) -> int:
    """Replace every demo booking with a fresh plan. Returns the number created. Safe to repeat."""
    with transaction.atomic():
        _, per_model = Booking.objects.filter(is_demo=True).delete()
    deleted = per_model.get(Booking._meta.label, 0)

    courts = list(Court.objects.filter(is_active=True).order_by("sort_order"))
    created: list[Booking] = []
    skipped = 0
    for p in plan(today=today, courts=courts, rng=rng):
        fields, created_at = _fields(p, now=now)
        spaces = rules.spaces_for(p.court, p.coverage, p.half)
        starts = rules.slot_starts(p.day, p.start_hour, p.hours)
        # SlotTaken and a reference clash propagate out of this atomic(), so the booking row is
        # rolled back together with its locks: a skipped demo booking leaves nothing behind.
        try:
            with transaction.atomic():
                booking = Booking.objects.create(reference=new_reference(), **fields)
                claim_slots(booking, spaces, starts, now=now)
        except SlotTaken:
            skipped += 1
            continue
        except IntegrityError as exc:
            if not _is_reference_clash(exc):
                raise
            skipped += 1
            continue
        # `created_at` is auto_now_add, so the realistic value is written afterwards in bulk.
        booking.created_at = created_at
        created.append(booking)

    Booking.objects.bulk_update(created, ["created_at"], batch_size=500)
    logger.info("demo.generated deleted=%d created=%d skipped=%d", deleted, len(created), skipped)
    return len(created)


def seed(*, now: datetime) -> int:
    """`generate` for today in Manila, seeded by the date, so the same day gives the same data."""
    today = rules.local_today(now)
    rng = random.Random(today.isoformat())  # noqa: S311 (demo data, not security)
    return generate(today=today, now=now, rng=rng)

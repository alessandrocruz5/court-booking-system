"""Pure builders for the storefront API's JSON bodies. The contract is pinned by
`docs/api/fixtures/*.json`; a change here updates the fixtures and both test suites.
"""

from datetime import date, datetime

from bookings import pricing, rules
from bookings.availability import CourtAvailability
from bookings.models import Booking
from bookings.rules import SPORTS, Sport

VENUE_NAME = "Kalaro Courts"
SPORT_ORDER = (
    Sport.BASKETBALL,
    Sport.VOLLEYBALL,
    Sport.TENNIS,
    Sport.BADMINTON,
    Sport.PICKLEBALL,
)


def catalog_payload() -> dict:
    """The venue, its rules and its rates. Built from constants only, never the database: every
    landing-page visit calls it, and a query would wake Neon."""
    rates = pricing.rate_table()
    sports = []
    for sport in SPORT_ORDER:
        rule = SPORTS[sport]
        sports.append(
            {
                "id": str(sport),
                "label": sport.label,
                "court_kind": str(rule.court_kind),
                "court_count": rules.COURT_COUNTS[rule.court_kind],
                "coverages": [str(coverage) for coverage in rule.coverages],
                "rates": {str(coverage): rates[sport][coverage] for coverage in rule.coverages},
            }
        )
    return {
        "venue": {"name": VENUE_NAME, "time_zone": rules.TIME_ZONE.key},
        "hours": {"open": rules.OPEN_HOUR, "close": rules.CLOSE_HOUR},
        "window_days": rules.WINDOW_DAYS,
        "max_hours": rules.MAX_HOURS,
        "hold_minutes": rules.HOLD_MINUTES,
        # Mirrors `pricing.is_peak`: weekends all day, and every day from PEAK_FROM_HOUR.
        "peak": {"weekdays_from_hour": pricing.PEAK_FROM_HOUR, "weekends_all_day": True},
        "sports": sports,
    }


def availability_payload(
    day: date, sport: str, coverage: str, hours: int, courts: list[CourtAvailability]
) -> dict:
    return {
        "date": day.isoformat(),
        "sport": str(sport),
        "coverage": str(coverage),
        "hours": hours,
        "courts": [
            {
                "code": court.code,
                "name": court.name,
                "starts": [
                    {
                        "hour": start.hour,
                        "price_centavos": start.price_centavos,
                        "peak": start.peak,
                    }
                    for start in court.starts
                ],
            }
            for court in courts
        ],
    }


def iso_local(value: datetime | None) -> str | None:
    """A timestamp as ISO-8601 in venue time (`+08:00`), or None."""
    return None if value is None else value.astimezone(rules.TIME_ZONE).isoformat()


def booking_summary(booking: Booking) -> dict:
    """What the success and lookup pages show. It never holds the customer's name, email or
    mobile (RA 10173)."""
    local_start = booking.starts_at.astimezone(rules.TIME_ZONE)
    return {
        "reference": booking.reference,
        "status": str(booking.status),
        "court": {"code": booking.court.code, "name": booking.court.name},
        "sport": None if booking.sport is None else str(booking.sport),
        "coverage": str(booking.coverage),
        "half": None if booking.half is None else str(booking.half),
        "date": local_start.date().isoformat(),
        "start_hour": local_start.hour,
        "hours": booking.hours,
        "price_centavos": booking.price_centavos,
        "hold_expires_at": iso_local(booking.hold_expires_at),
        "paid_at": iso_local(booking.paid_at),
        "payment_method": booking.payment_method or None,
    }

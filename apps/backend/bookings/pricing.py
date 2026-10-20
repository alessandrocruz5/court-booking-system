"""Price quotes in integer centavos. The quote is computed here, on the server, and snapshotted on
the booking; the paid amount is later checked against that snapshot.
"""

from datetime import date

from bookings.rules import Coverage, Sport

PEAK_FROM_HOUR = 17

# (sport, coverage) -> (off_peak, peak) centavos per hour.
RATES: dict[tuple[str, str], tuple[int, int]] = {
    (Sport.BASKETBALL, Coverage.FULL): (120_000, 160_000),
    (Sport.BASKETBALL, Coverage.HALF): (70_000, 90_000),
    (Sport.VOLLEYBALL, Coverage.FULL): (120_000, 160_000),
    (Sport.TENNIS, Coverage.FULL): (50_000, 70_000),
    (Sport.BADMINTON, Coverage.FULL): (35_000, 45_000),
    (Sport.PICKLEBALL, Coverage.FULL): (40_000, 50_000),
}


def is_peak(day: date, hour: int) -> bool:
    """Saturdays and Sundays all day, and every day from 17:00."""
    return day.weekday() >= 5 or hour >= PEAK_FROM_HOUR


def quote(sport: str, coverage: str, day: date, start_hour: int, hours: int) -> int:
    off_peak, peak = RATES[(sport, coverage)]
    return sum(
        peak if is_peak(day, hour) else off_peak for hour in range(start_hour, start_hour + hours)
    )


def rate_table() -> dict[str, dict[str, dict[str, int]]]:
    """`{sport: {coverage: {"off_peak": c, "peak": c}}}` for the catalog."""
    table: dict[str, dict[str, dict[str, int]]] = {}
    for (sport, coverage), (off_peak, peak) in RATES.items():
        table.setdefault(str(sport), {})[str(coverage)] = {"off_peak": off_peak, "peak": peak}
    return table

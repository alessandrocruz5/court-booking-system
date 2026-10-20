from datetime import date

from bookings import pricing
from bookings.rules import SPORTS

MONDAY = date(2026, 11, 2)
SATURDAY = date(2026, 11, 7)


def test_weekday_peak_starts_at_17():
    assert MONDAY.weekday() == 0
    assert not pricing.is_peak(MONDAY, 16)
    assert pricing.is_peak(MONDAY, 17)
    assert pricing.is_peak(MONDAY, 22)


def test_weekends_are_peak_all_day():
    assert SATURDAY.weekday() == 5
    assert pricing.is_peak(SATURDAY, 8)
    assert pricing.is_peak(date(2026, 11, 8), 7)


def test_span_across_17_sums_off_peak_and_peak():
    assert pricing.quote("tennis", "full", MONDAY, 16, 2) == 50_000 + 70_000
    assert pricing.quote("basketball", "half", MONDAY, 15, 3) == 70_000 * 2 + 90_000
    assert pricing.quote("badminton", "full", SATURDAY, 8, 1) == 45_000


def test_every_sport_and_coverage_has_a_rate():
    pairs = {(sport, coverage) for sport, rule in SPORTS.items() for coverage in rule.coverages}
    assert pairs == set(pricing.RATES)
    for off_peak, peak in pricing.RATES.values():
        assert 0 < off_peak < peak


def test_rate_table_shape():
    table = pricing.rate_table()
    assert table["basketball"] == {
        "full": {"off_peak": 120_000, "peak": 160_000},
        "half": {"off_peak": 70_000, "peak": 90_000},
    }
    assert table["volleyball"] == {"full": {"off_peak": 120_000, "peak": 160_000}}
    assert table["tennis"] == {"full": {"off_peak": 50_000, "peak": 70_000}}
    assert table["badminton"] == {"full": {"off_peak": 35_000, "peak": 45_000}}
    assert table["pickleball"] == {"full": {"off_peak": 40_000, "peak": 50_000}}
    assert all(type(key) is str for key in table)

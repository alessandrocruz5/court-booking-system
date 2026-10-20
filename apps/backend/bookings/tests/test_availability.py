from datetime import date, datetime, timedelta

import pytest

from bookings import holds, rules
from bookings.availability import CourtAvailability, StartOption, availability, occupancy
from bookings.models import Court
from bookings.rules import BookingRuleError

# Monday 2 November 2026, 10:00 in Manila.
NOW = datetime(2026, 11, 2, 10, tzinfo=rules.TIME_ZONE)
TODAY = date(2026, 11, 2)
TOMORROW = TODAY + timedelta(days=1)
CUSTOMER = holds.Customer(name="Test Visitor", email="visitor@example.com", mobile="+639000000001")


def hours_for(result: list[CourtAvailability], code: str) -> list[int]:
    (court,) = [c for c in result if c.code == code]
    return [start.hour for start in court.starts]


def walk_in(court: Court, sport: str, coverage: str, half: str | None, start_hour: int):
    return holds.create_staff_booking(
        source="walk_in",
        court=court,
        sport=sport,
        coverage=coverage,
        half=half,
        day=TOMORROW,
        start_hour=start_hour,
        hours=1,
        created_by=None,
        now=NOW,
    )


@pytest.mark.django_db
def test_lists_only_the_sports_courts_in_order():
    tennis = availability(day=TOMORROW, sport="tennis", coverage="full", hours=1, now=NOW)
    assert [c.code for c in tennis] == ["tn-1", "tn-2", "tn-3", "tn-4"]
    badminton = availability(day=TOMORROW, sport="badminton", coverage="full", hours=1, now=NOW)
    assert [c.code for c in badminton] == [f"mp-{n:02d}" for n in range(1, 13)]
    volleyball = availability(day=TOMORROW, sport="volleyball", coverage="full", hours=1, now=NOW)
    assert [c.code for c in volleyball] == ["bb-1", "bb-2"]


@pytest.mark.django_db
def test_skips_inactive_courts():
    Court.objects.filter(code="tn-2").update(is_active=False)
    result = availability(day=TOMORROW, sport="tennis", coverage="full", hours=1, now=NOW)
    assert [c.code for c in result] == ["tn-1", "tn-3", "tn-4"]


@pytest.mark.django_db
def test_free_day_offers_every_start_with_prices():
    result = availability(day=TOMORROW, sport="tennis", coverage="full", hours=2, now=NOW)
    starts = result[0].starts
    assert [s.hour for s in starts] == list(range(7, 22))
    assert starts[0] == StartOption(hour=7, price_centavos=100_000, peak=False)
    assert StartOption(hour=16, price_centavos=120_000, peak=False) in starts
    assert StartOption(hour=17, price_centavos=140_000, peak=True) in starts


@pytest.mark.django_db
def test_hours_past_close_are_omitted():
    one = availability(day=TOMORROW, sport="tennis", coverage="full", hours=1, now=NOW)
    three = availability(day=TOMORROW, sport="tennis", coverage="full", hours=3, now=NOW)
    assert max(hours_for(one, "tn-1")) == 22
    assert max(hours_for(three, "tn-1")) == 20


@pytest.mark.django_db
def test_today_omits_started_hours():
    result = availability(day=TODAY, sport="tennis", coverage="full", hours=1, now=NOW)
    assert hours_for(result, "tn-1")[0] == 11


@pytest.mark.django_db
def test_confirmed_full_basketball_blocks_full_and_half():
    bb1 = Court.objects.get(code="bb-1")
    walk_in(bb1, "basketball", "full", None, 12)

    for sport, coverage in [("basketball", "full"), ("basketball", "half"), ("volleyball", "full")]:
        result = availability(day=TOMORROW, sport=sport, coverage=coverage, hours=1, now=NOW)
        assert 12 not in hours_for(result, "bb-1")
        assert 12 in hours_for(result, "bb-2")
    two_hours = availability(day=TOMORROW, sport="basketball", coverage="half", hours=2, now=NOW)
    assert 11 not in hours_for(two_hours, "bb-1")


@pytest.mark.django_db
def test_half_a_booked_leaves_half_b_but_not_full():
    bb1 = Court.objects.get(code="bb-1")
    walk_in(bb1, "basketball", "half", "A", 12)

    half = availability(day=TOMORROW, sport="basketball", coverage="half", hours=1, now=NOW)
    full = availability(day=TOMORROW, sport="basketball", coverage="full", hours=1, now=NOW)
    assert 12 in hours_for(half, "bb-1")
    assert 12 not in hours_for(full, "bb-1")

    walk_in(bb1, "basketball", "half", "B", 12)
    half = availability(day=TOMORROW, sport="basketball", coverage="half", hours=1, now=NOW)
    assert 12 not in hours_for(half, "bb-1")


@pytest.mark.django_db
def test_half_span_needs_one_half_free_throughout():
    bb1 = Court.objects.get(code="bb-1")
    walk_in(bb1, "basketball", "half", "A", 12)
    walk_in(bb1, "basketball", "half", "B", 13)

    # 12-14 has A taken at 12 and B taken at 13: neither half is free for the whole span.
    result = availability(day=TOMORROW, sport="basketball", coverage="half", hours=2, now=NOW)
    assert 12 not in hours_for(result, "bb-1")
    assert 14 in hours_for(result, "bb-1")


@pytest.mark.django_db
def test_expired_pending_hold_counts_as_free():
    tn1 = Court.objects.get(code="tn-1")
    holds.create_hold(
        court=tn1,
        sport="tennis",
        coverage="full",
        day=TOMORROW,
        start_hour=12,
        hours=1,
        customer=CUSTOMER,
        now=NOW,
    )
    during = availability(day=TOMORROW, sport="tennis", coverage="full", hours=1, now=NOW)
    assert 12 not in hours_for(during, "tn-1")

    later = NOW + timedelta(minutes=rules.HOLD_MINUTES)
    after = availability(day=TOMORROW, sport="tennis", coverage="full", hours=1, now=later)
    assert 12 in hours_for(after, "tn-1")


@pytest.mark.django_db
def test_released_booking_frees_its_slots():
    tn1 = Court.objects.get(code="tn-1")
    booking = walk_in(tn1, "tennis", "full", None, 12)
    holds.release(booking, status="cancelled", now=NOW)

    result = availability(day=TOMORROW, sport="tennis", coverage="full", hours=1, now=NOW)
    assert 12 in hours_for(result, "tn-1")


@pytest.mark.django_db
def test_uses_two_queries(django_assert_num_queries):
    with django_assert_num_queries(2):
        availability(day=TOMORROW, sport="badminton", coverage="full", hours=3, now=NOW)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        pytest.param({"sport": "curling"}, "unknown_sport", id="sport"),
        pytest.param({"sport": "volleyball", "coverage": "half"}, "coverage_not_allowed", id="cov"),
        pytest.param({"hours": 4}, "invalid_hours", id="hours"),
        pytest.param({"day": TODAY + timedelta(days=7)}, "outside_window", id="day"),
    ],
)
def test_bad_inputs_raise(kwargs, code):
    args = {"day": TOMORROW, "sport": "tennis", "coverage": "full", "hours": 1, "now": NOW}
    args.update(kwargs)
    with pytest.raises(BookingRuleError) as info:
        availability(**args)
    assert info.value.code == code


@pytest.mark.django_db
def test_occupancy_maps_active_locks_to_bookings():
    bb1 = Court.objects.get(code="bb-1")
    tn1 = Court.objects.get(code="tn-1")
    full = walk_in(bb1, "basketball", "full", None, 12)
    hold = holds.create_hold(
        court=tn1,
        sport="tennis",
        coverage="full",
        day=TOMORROW,
        start_hour=15,
        hours=2,
        customer=CUSTOMER,
        now=NOW,
    )

    grid = occupancy(TOMORROW, now=NOW)
    assert grid == {
        (bb1.pk, "A", 12): full,
        (bb1.pk, "B", 12): full,
        (tn1.pk, "F", 15): hold,
        (tn1.pk, "F", 16): hold,
    }
    assert occupancy(TODAY, now=NOW) == {}
    # Once the hold lapses it no longer occupies the grid.
    later = occupancy(TOMORROW, now=NOW + timedelta(minutes=rules.HOLD_MINUTES))
    assert set(later) == {(bb1.pk, "A", 12), (bb1.pk, "B", 12)}

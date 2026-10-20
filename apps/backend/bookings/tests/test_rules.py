from datetime import UTC, date, datetime, timedelta

import pytest

from bookings import rules
from bookings.models import Court
from bookings.rules import BookingRuleError

# Monday 2 November 2026, 10:00 in Manila.
NOW = datetime(2026, 11, 2, 10, tzinfo=rules.TIME_ZONE)
TODAY = date(2026, 11, 2)

TENNIS = Court(code="tn-1", name="Tennis Court 1", kind="tennis", sort_order=20)
BASKETBALL = Court(code="bb-1", name="Basketball Court 1", kind="basketball", sort_order=10)


def customer(**overrides) -> None:
    kwargs = {
        "court": TENNIS,
        "sport": "tennis",
        "coverage": "full",
        "day": TODAY + timedelta(days=1),
        "start_hour": 9,
        "hours": 1,
        "now": NOW,
    }
    kwargs.update(overrides)
    rules.validate_customer_request(**kwargs)


def staff(**overrides) -> None:
    kwargs = {
        "court": TENNIS,
        "sport": "tennis",
        "coverage": "full",
        "day": TODAY,
        "start_hour": 12,
        "hours": 1,
        "now": NOW,
    }
    kwargs.update(overrides)
    rules.validate_staff_request(**kwargs)


def code_of(check, **overrides) -> str:
    with pytest.raises(BookingRuleError) as info:
        check(**overrides)
    return info.value.code


def test_fixed_now_is_a_monday():
    assert TODAY.weekday() == 0
    assert rules.local_today(NOW) == TODAY


def test_valid_customer_request_passes():
    customer()
    customer(court=BASKETBALL, sport="basketball", coverage="half")
    customer(court=BASKETBALL, sport="volleyball", coverage="full")


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        pytest.param({"sport": "curling"}, "unknown_sport", id="unknown_sport"),
        pytest.param(
            {"court": Court(code="tn-9", kind="tennis", sort_order=1, is_active=False)},
            "court_inactive",
            id="court_inactive",
        ),
        pytest.param({"sport": "badminton"}, "wrong_court_for_sport", id="badminton_on_tennis"),
        pytest.param(
            {"court": BASKETBALL, "sport": "volleyball", "coverage": "half"},
            "coverage_not_allowed",
            id="volleyball_half",
        ),
        pytest.param({"coverage": "half"}, "coverage_not_allowed", id="tennis_half"),
        pytest.param({"hours": 0}, "invalid_hours", id="hours_0"),
        pytest.param({"hours": 4}, "invalid_hours", id="hours_4"),
        pytest.param({"start_hour": 6}, "outside_hours", id="before_open"),
        pytest.param({"start_hour": 23}, "outside_hours", id="start_at_close"),
        pytest.param({"start_hour": 22, "hours": 2}, "outside_hours", id="22_for_2h"),
        pytest.param({"day": TODAY + timedelta(days=7)}, "outside_window", id="day_7"),
        pytest.param({"day": TODAY - timedelta(days=1)}, "outside_window", id="yesterday"),
        pytest.param({"day": TODAY, "start_hour": 10}, "in_the_past", id="starts_now"),
        pytest.param({"day": TODAY, "start_hour": 8}, "in_the_past", id="already_passed"),
    ],
)
def test_customer_request_errors(overrides, code):
    assert code_of(customer, **overrides) == code


def test_last_start_is_22_for_one_hour():
    customer(start_hour=22, hours=1)
    assert code_of(customer, start_hour=22, hours=2) == "outside_hours"
    customer(start_hour=20, hours=3)


def test_window_is_today_through_day_6():
    assert rules.bookable_dates(NOW) == [TODAY + timedelta(days=n) for n in range(7)]
    customer(day=TODAY + timedelta(days=6))
    customer(day=TODAY, start_hour=11)
    assert code_of(customer, day=TODAY + timedelta(days=7)) == "outside_window"


def test_window_uses_manila_date():
    # 23:30 UTC on Sunday is already Monday 07:30 in Manila.
    assert rules.local_today(datetime(2026, 11, 1, 23, 30, tzinfo=UTC)) == TODAY


def test_slot_starts_are_aware_and_hourly():
    starts = rules.slot_starts(TODAY, 20, 3)
    assert starts == [datetime(2026, 11, 2, h, tzinfo=rules.TIME_ZONE) for h in (20, 21, 22)]
    assert all(start.utcoffset() == timedelta(hours=8) for start in starts)


def test_spaces_for():
    assert rules.spaces_for(BASKETBALL, "full", None) == ["A", "B"]
    assert rules.spaces_for(BASKETBALL, "half", "B") == ["B"]
    assert rules.spaces_for(TENNIS, "full", None) == ["F"]
    multi = Court(code="mp-01", kind="multi", sort_order=30)
    assert rules.spaces_for(multi, "full", None) == ["F"]
    with pytest.raises(ValueError):
        rules.spaces_for(BASKETBALL, "half", None)


def test_staff_window_allows_plus_30_but_not_31():
    staff(day=TODAY + timedelta(days=30))
    assert code_of(staff, day=TODAY + timedelta(days=31)) == "outside_window"
    assert code_of(staff, day=TODAY - timedelta(days=1)) == "outside_window"


def test_staff_can_log_the_hour_in_progress():
    half_past = NOW + timedelta(minutes=30)
    staff(start_hour=10, now=half_past)
    staff(start_hour=9, hours=2, now=half_past)
    assert code_of(staff, start_hour=9, hours=1, now=half_past) == "in_the_past"
    assert code_of(customer, day=TODAY, start_hour=10, now=half_past) == "in_the_past"


def test_staff_block_has_no_sport():
    staff(sport=None)
    staff(court=BASKETBALL, sport=None)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        pytest.param({"sport": "curling"}, "unknown_sport", id="unknown_sport"),
        pytest.param(
            {"court": Court(code="tn-9", kind="tennis", sort_order=1, is_active=False)},
            "court_inactive",
            id="court_inactive",
        ),
        pytest.param({"sport": "pickleball"}, "wrong_court_for_sport", id="wrong_court"),
        pytest.param(
            {"court": BASKETBALL, "sport": "volleyball", "coverage": "half"},
            "coverage_not_allowed",
            id="volleyball_half",
        ),
        pytest.param({"hours": 4}, "invalid_hours", id="hours_4"),
        pytest.param({"start_hour": 22, "hours": 2}, "outside_hours", id="past_close"),
    ],
)
def test_staff_request_errors(overrides, code):
    assert code_of(staff, **overrides) == code


def test_error_exposes_code():
    error = BookingRuleError("outside_window")
    assert error.code == "outside_window"
    assert str(error) == "outside_window"

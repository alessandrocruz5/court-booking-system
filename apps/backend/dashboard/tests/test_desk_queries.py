from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from django.http import QueryDict

from accounts.roles import Role, can_check_in
from bookings import rules
from bookings.checkin import CheckInError, check_in
from bookings.models import Booking, Court
from bookings.rules import Source, Status
from dashboard import desk, queries
from dashboard.desk import normalise_query
from dashboard.tests import test_overview as overview_helpers
from dashboard.tests.test_bookings import (  # noqa: F401 (`pinned_clock`: an autouse fixture)
    EMAIL,
    MOBILE,
    NAME,
    NOW,
    TODAY,
    listed,
    make,
    make_user,
    pinned_clock,
)

DEMO_NAME = "Maria Santos"
HOLD_ENDS = NOW + timedelta(minutes=15)  # A pending booking needs a live hold.


def at(hour: int, day=TODAY) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=rules.TIME_ZONE)


def court(code: str) -> Court:
    return Court.objects.get(code=code)


# --- normalising ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (" w3pe7v ", "KC-W3PE7V"),
        ("kc-w3pe7v", "KC-W3PE7V"),
        ("KC-W3PE7V", "KC-W3PE7V"),
        ("w3pe7", "W3PE7"),  # Too short to be a reference.
        ("w3pe7vx", "W3PE7VX"),  # Too long.
        ("w3pe7i", "W3PE7I"),  # I and U aren't Crockford.
        ("w3pe7u", "W3PE7U"),
        ("maria", "MARIA"),
        ("kc w3pe7v", "KC W3PE7V"),
        ("KC-W3P\x00E7V", ""),
        ("\x00", ""),
        ("   ", ""),
        (None, ""),
    ],
)
def test_normalise_query(text, expected):
    assert normalise_query(text) == expected


# --- lookup --------------------------------------------------------------------------------------


@pytest.mark.django_db
class TestLookup:
    def test_owner_sees_the_customer_raw(self):
        make("KC-T00001")

        result = desk.lookup(Role.OWNER, " t00001 ", NOW)

        assert result.reference == "KC-T00001"
        assert (result.name, result.contact) == (NAME, f"{EMAIL} · {MOBILE}")
        assert (result.status_key, result.status_label, result.pill) == (
            "confirmed",
            "Confirmed",
            "pill-confirmed",
        )
        assert (result.amount, result.court, result.sport, result.time) == (
            "₱300",
            "Court 1",
            "Badminton · full",
            "2 PM – 3 PM",
        )
        assert result.warning is None
        assert result.can_check_in
        assert result.checked_in_clock == ""
        assert result.schedule_day == TODAY

    def test_viewer_sees_the_customer_masked(self):
        make("KC-T00001")

        result = desk.lookup(Role.VIEWER, "KC-T00001", NOW)

        assert (result.name, result.contact) == ("Juan D.", "j•••@example.com · •••67")
        assert NAME not in result.contact and EMAIL not in result.contact
        # A real visitor's online booking: the viewer can't check it in.
        assert not result.can_check_in

    def test_viewer_can_check_in_a_demo_booking(self):
        make("KC-T00001", is_demo=True)

        assert desk.lookup(Role.VIEWER, "KC-T00001", NOW).can_check_in

    def test_a_walk_in_without_contact_has_an_empty_contact(self):
        make("KC-T00001", source=Source.WALK_IN, customer_email=None, customer_mobile=None)

        assert desk.lookup(Role.VIEWER, "KC-T00001", NOW).contact == ""

    @pytest.mark.parametrize("text", ["KC-T00002", "T0000", "Juan Dela Cruz", "KC-T0\x000001", ""])
    def test_only_an_exact_reference_matches(self, text):
        make("KC-T00001")

        assert desk.lookup(Role.OWNER, text, NOW) is None


@pytest.mark.django_db
class TestWarnings:
    def warning(self, **fields):
        make("KC-T00001", **fields)
        return desk.lookup(Role.OWNER, "KC-T00001", NOW)

    def test_another_day(self):
        result = self.warning(day=TODAY + timedelta(days=1))

        assert result.warning == "This booking is for Tuesday 3 Nov — not today."
        assert result.time == "Tue 3, 2 PM – 3 PM"
        assert result.schedule_day == TODAY + timedelta(days=1)
        assert not result.can_check_in

    def test_another_day_comes_before_ended(self):
        result = self.warning(day=TODAY - timedelta(days=1))

        assert result.warning == "This booking is for Sunday 1 Nov — not today."
        assert result.status_key == "completed"

    def test_pending(self):
        result = self.warning(status=Status.PENDING, hold_expires_at=HOLD_ENDS)

        assert result.warning == "Payment not received yet. The slot is on a 20-minute hold."
        assert result.status_label == "Pending"

    def test_pending_with_a_lapsed_hold(self):
        result = self.warning(status=Status.PENDING, hold_expires_at=NOW - timedelta(minutes=1))

        assert result.warning == "Payment not received, and the hold has lapsed."

    def test_running_late(self):
        result = self.warning(hour=11, ends_at=at(13), hours=2)

        assert result.warning == "Running late — started at 11 AM. Ends 1 PM."
        assert result.time == "11 AM – 1 PM"
        assert result.can_check_in

    def test_ended(self):
        result = self.warning(hour=9)

        assert result.warning == "This session has already ended."
        assert (result.status_key, result.status_label) == ("completed", "Completed")
        assert not result.can_check_in

    def test_checked_in_and_on_court_has_no_warning(self):
        result = self.warning(
            hour=11, ends_at=at(13), hours=2, checked_in_at=at(11) + timedelta(minutes=5)
        )

        assert result.warning is None
        assert (result.status_key, result.status_label) == ("checked_in", "Checked in")
        assert result.checked_in_clock == "11:05 AM"
        assert not result.can_check_in

    def test_cancelled_has_no_warning(self):
        result = self.warning(hour=9, status=Status.CANCELLED)

        assert result.warning is None
        assert result.status_key == "cancelled"

    def test_a_block_is_blocked(self):
        result = self.warning(
            source=Source.BLOCK,
            sport=None,
            price_centavos=0,
            customer_name="",
            customer_email=None,
            customer_mobile=None,
            note="Maintenance",
        )

        assert (result.status_key, result.status_label, result.sport) == ("block", "Blocked", "")
        assert (result.amount, result.warning) == ("", None)
        assert not result.can_check_in

    @pytest.mark.parametrize(
        "when",
        [
            {"hour": 11, "ends_at": at(13), "hours": 2},  # In progress.
            {"day": TODAY + timedelta(days=1)},
            {"hour": 9},  # Ended.
        ],
    )
    def test_a_block_never_gets_a_customer_warning(self, when):
        result = self.warning(
            source=Source.BLOCK,
            sport=None,
            price_centavos=0,
            customer_name="",
            customer_email=None,
            customer_mobile=None,
            note="Maintenance",
            **when,
        )

        assert result.warning is None


# --- suggestions ---------------------------------------------------------------------------------


@pytest.mark.django_db
class TestSuggest:
    @pytest.fixture(autouse=True)
    def bookings(self):
        make("KC-T00001", customer_name=DEMO_NAME, is_demo=True, hour=18)
        make("KC-T00002", customer_name="Maria Clara", hour=15)  # A real customer.
        make("KC-T00003", customer_name="Maria Lopez", day=TODAY - timedelta(days=1))  # Past.
        make(
            "KC-T00004",
            source=Source.BLOCK,
            sport=None,
            price_centavos=0,
            customer_name="",
            customer_email=None,
            customer_mobile=None,
            note="Maria's party",
            hour=16,
        )

    def refs(self, role, text):
        return [row.reference for row in desk.suggest(role, text, NOW)]

    def test_viewer_matches_demo_names_only(self):
        assert self.refs(Role.VIEWER, "maria") == ["KC-T00001"]
        assert self.refs(Role.VIEWER, "Maria Clara") == []
        assert self.refs(Role.VIEWER, "clara") == []

    def test_viewer_never_matches_contact_details(self):
        assert self.refs(Role.VIEWER, EMAIL) == []
        assert self.refs(Role.VIEWER, "9171234567") == []

    def test_owner_matches_every_name_earliest_first(self):
        assert self.refs(Role.OWNER, "maria") == ["KC-T00002", "KC-T00001"]

    def test_references_match_and_blocks_and_past_days_never_do(self):
        assert self.refs(Role.VIEWER, "t0000") == ["KC-T00002", "KC-T00001"]

    def test_rows_are_masked_for_the_viewer(self):
        (row,) = desk.suggest(Role.VIEWER, "KC-T00002", NOW)

        assert (row.name, row.when) == ("Maria C.", "Today, 3 PM – 4 PM")

    def test_limit(self):
        assert len(desk.suggest(Role.OWNER, "maria", NOW, limit=1)) == 1

    @pytest.mark.parametrize("text", ["", "  ", "m", "K", "ma\x00ria", None])
    def test_empty_or_nul_suggests_nothing(self, text):
        assert desk.suggest(Role.OWNER, text, NOW) == ()


# --- arriving and on court -----------------------------------------------------------------------


@pytest.mark.django_db
class TestArrivingAndOnCourt:
    @pytest.fixture(autouse=True)
    def bookings(self):
        make("KC-A00001", court=court("mp-01"), hour=11, ends_at=at(13), hours=2)  # Late.
        make("KC-A00002", court=court("mp-02"), hour=12, is_demo=True)  # Starts now.
        make("KC-A00003", court=court("mp-03"), hour=13, source=Source.WALK_IN)
        make("KC-A00004", court=court("mp-04"), hour=14)
        make("KC-A00005", court=court("mp-05"), hour=15)  # Outside the 3 hours.
        make("KC-A00006", court=court("mp-06"), hour=10)  # Ended.
        make(
            "KC-A00007",
            court=court("mp-07"),
            hour=13,
            status=Status.PENDING,
            hold_expires_at=HOLD_ENDS,
        )
        make("KC-A00008", court=court("mp-08"), hour=13, status=Status.CANCELLED)
        make("KC-A00009", court=court("mp-09"), hour=13, day=TODAY + timedelta(days=1))
        make(
            "KC-A00010",
            court=court("mp-10"),
            hour=12,
            ends_at=at(14),
            hours=2,
            checked_in_at=at(11) + timedelta(minutes=55),
        )
        make(
            "KC-A00011",
            court=court("mp-11"),
            hour=13,
            source=Source.BLOCK,
            sport=None,
            price_centavos=0,
            customer_name="",
            customer_email=None,
            customer_mobile=None,
            note="Maintenance",
        )
        # Checked in, then cancelled: neither arriving nor on court.
        make("KC-A00012", court=court("mp-12"), hour=12, status=Status.CANCELLED, checked_in_at=NOW)

    def test_arriving_window_and_tags(self):
        rows = desk.arriving(Role.OWNER, NOW)

        assert [(row.reference, row.tag, row.starts) for row in rows] == [
            ("KC-A00001", "late", "11 AM"),
            ("KC-A00002", "next", "12 PM"),
            ("KC-A00003", "next", "1 PM"),
            ("KC-A00004", "", "2 PM"),
        ]
        assert all(row.can_check_in for row in rows)
        assert rows[0].court == "Court 1" and rows[0].sport == "badminton"

    def test_the_window_is_injectable(self):
        refs = [row.reference for row in desk.arriving(Role.OWNER, NOW, within_hours=1)]

        assert refs == ["KC-A00001", "KC-A00002"]

    def test_arriving_is_masked_and_permissioned_for_the_viewer(self):
        rows = {row.reference: row for row in desk.arriving(Role.VIEWER, NOW)}

        assert rows["KC-A00001"].name == "Juan D."
        assert not rows["KC-A00001"].can_check_in  # A real online booking.
        assert rows["KC-A00002"].can_check_in and rows["KC-A00002"].is_demo
        assert rows["KC-A00003"].can_check_in  # A walk-in.

    def test_on_court(self):
        (row,) = desk.on_court(Role.VIEWER, NOW)

        assert (row.reference, row.status_key, row.ends) == ("KC-A00010", "checked_in", "2 PM")
        assert row.name == "Juan D."
        assert not row.can_check_in

    def test_an_early_check_in_stays_arriving_until_it_starts(self):
        make("KC-A00013", court=court("mp-11"), hour=14, checked_in_at=NOW)

        arriving = {row.reference: row for row in desk.arriving(Role.OWNER, NOW)}
        assert arriving["KC-A00013"].status_key == "checked_in"
        assert not arriving["KC-A00013"].can_check_in
        assert "KC-A00013" not in [row.reference for row in desk.on_court(Role.OWNER, NOW)]


# --- stats ---------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_stats_reuse_the_overviews_aggregates():
    walk = overview_helpers.walk_in("mp-01", hour=11, hours=2)  # On court at 12.
    now_paid = overview_helpers.online("mp-02", hour=12)
    early = overview_helpers.online("mp-03", hour=9)  # Ended, still today's.
    overview_helpers.block("mp-04", hour=12)  # Not in use by anyone.
    # A live hold, made at 12:20, so it still holds at 12:30.
    overview_helpers.online("mp-05", hour=15, confirm=False, now=NOW + timedelta(minutes=20))
    overview_helpers.walk_in("mp-06", day=TODAY + timedelta(days=1), hour=12)

    stats = desk.stats(NOW + timedelta(minutes=30))

    today = queries._today(NOW)
    assert stats.bookings == today.bookings == 3
    assert stats.walk_ins == 1
    assert stats.revenue == today.revenue
    assert stats.revenue == walk.price_centavos + now_paid.price_centavos + early.price_centavos
    assert stats.revenue_display == queries.peso(stats.revenue)
    assert (stats.spaces_in_use, stats.space_count) == (2, 20)
    assert stats.active_holds == 1


# --- status_key and the list's filters -----------------------------------------------------------


def _key(status="confirmed", source="online", ends_at=NOW + timedelta(hours=1), checked_in_at=None):
    booking = SimpleNamespace(
        status=status, source=source, ends_at=ends_at, checked_in_at=checked_in_at
    )
    return queries.status_key(booking, NOW)


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({}, "confirmed"),
        ({"checked_in_at": NOW}, "checked_in"),
        # Ended wins over checked in.
        ({"checked_in_at": NOW - timedelta(hours=2), "ends_at": NOW}, "completed"),
        ({"ends_at": NOW - timedelta(hours=1)}, "completed"),
        ({"source": "block"}, "block"),
        ({"source": "block", "ends_at": NOW - timedelta(hours=1)}, "block"),
        ({"status": "pending"}, "pending"),
        ({"status": "cancelled", "checked_in_at": NOW}, "cancelled"),
        ({"status": "cancelled", "ends_at": NOW - timedelta(hours=1)}, "cancelled"),
        ({"status": "needs_refund"}, "needs_refund"),
        ({"status": "expired", "ends_at": NOW - timedelta(hours=1)}, "expired"),
    ],
)
def test_status_key(fields, expected):
    assert _key(**fields) == expected


@pytest.mark.django_db
class TestDerivedFilters:
    @pytest.fixture(autouse=True)
    def bookings(self):
        make("KC-F00001", hour=12, checked_in_at=NOW)  # Checked in, on court.
        make("KC-F00002", hour=9, checked_in_at=at(9))  # Checked in, ended.
        make("KC-F00003", hour=10)  # Ended, never checked in.
        make("KC-F00004", hour=15)  # Still to come.
        make("KC-F00005", hour=9, day=TODAY - timedelta(days=3))  # Ended days ago.
        make("KC-F00006", hour=11, status=Status.CANCELLED, checked_in_at=at(11))
        make(
            "KC-F00007",
            hour=8,
            source=Source.BLOCK,
            sport=None,
            price_centavos=0,
            customer_name="",
            customer_email=None,
            customer_mobile=None,
            note="Maintenance",
        )

    def refs(self, status):
        params = queries.parse_list_params(QueryDict(f"status={status}&sort=starts_at"))
        page = queries.list_bookings(role=Role.OWNER, params=params, now=NOW)
        return [row.reference for row in page.rows]

    def test_the_new_statuses_are_valid_choices(self):
        assert ("checked_in", "Checked in") in queries.STATUS_CHOICES
        assert ("completed", "Completed") in queries.STATUS_CHOICES
        for status in ("checked_in", "completed", "confirmed", "needs_refund"):
            assert queries.parse_list_params(QueryDict(f"status={status}")).status == status
        assert queries.parse_list_params(QueryDict("status=block")).status is None

    def test_checked_in(self):
        assert self.refs("checked_in") == ["KC-F00001"]

    def test_completed(self):
        assert self.refs("completed") == ["KC-F00005", "KC-F00002", "KC-F00003"]

    def test_plain_confirmed_still_lists_ended_and_checked_in_bookings(self):
        assert self.refs("confirmed") == [
            "KC-F00005",
            "KC-F00007",
            "KC-F00002",
            "KC-F00003",
            "KC-F00001",
            "KC-F00004",
        ]

    def test_the_view_filters_on_the_pinned_clock(self, client):
        client.force_login(make_user(Role.OWNER))

        assert listed(client, status="checked_in") == ["KC-F00001"]
        assert sorted(listed(client, status="completed")) == ["KC-F00002", "KC-F00003", "KC-F00005"]
        assert len(listed(client, status="confirmed")) == 6

    def test_rows_and_detail_expose_the_derived_status(self):
        params = queries.parse_list_params(QueryDict("sort=starts_at"))
        rows = {
            row.reference: row
            for row in queries.list_bookings(role=Role.OWNER, params=params, now=NOW).rows
        }

        assert (rows["KC-F00001"].status, rows["KC-F00001"].status_key) == (
            "confirmed",
            "checked_in",
        )
        assert rows["KC-F00001"].checked_in_clock == "12:00 PM"
        assert rows["KC-F00003"].status_key == "completed"
        assert rows["KC-F00003"].checked_in_clock == ""
        assert rows["KC-F00007"].status_key == "block"
        detail = queries.get_booking(role=Role.OWNER, reference="KC-F00002", now=NOW)
        assert (detail.status_key, detail.checked_in_clock) == ("completed", "9:00 AM")
        assert not detail.can_check_in

    def test_detail_can_check_in_follows_the_role(self):
        make("KC-F00008", hour=14, is_demo=True)
        make("KC-F00009", hour=14, court=court("mp-02"))

        get = queries.get_booking
        assert get(role=Role.OWNER, reference="KC-F00009", now=NOW).can_check_in
        assert not get(role=Role.VIEWER, reference="KC-F00009", now=NOW).can_check_in
        assert get(role=Role.VIEWER, reference="KC-F00008", now=NOW).can_check_in
        assert not get(
            role=Role.OWNER, reference="KC-F00004", now=NOW + timedelta(days=1)
        ).can_check_in


# --- can_check_in matches check_in ---------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_check_in_exactly_when_check_in_succeeds():
    """`roles.can_check_in` restates `checkin.check_in`'s rules; this keeps the two in step."""
    by = make_user(Role.OWNER)
    bookings = [
        make("KC-P00001", hour=14),
        make("KC-P00002", hour=11, ends_at=at(13), hours=2),
        make("KC-P00003", hour=10),
        make("KC-P00004", hour=14, day=TODAY + timedelta(days=1)),
        make("KC-P00005", hour=14, status=Status.PENDING, hold_expires_at=HOLD_ENDS),
        make("KC-P00006", hour=14, status=Status.CANCELLED),
        make("KC-P00007", hour=14, checked_in_at=NOW),
        make("KC-P00008", hour=14, source=Source.WALK_IN, is_demo=True),
        make(
            "KC-P00009",
            hour=14,
            source=Source.BLOCK,
            sport=None,
            price_centavos=0,
            customer_name="",
            customer_email=None,
            customer_mobile=None,
            note="Maintenance",
        ),
    ]
    for booking in bookings:
        allowed = can_check_in(Role.OWNER, booking, now=NOW)
        try:
            checked_in = check_in(booking, by=by, now=NOW)
        except CheckInError:
            checked_in = False
        assert allowed is checked_in, booking.reference
    assert Booking.objects.filter(checked_in_at=NOW).count() == 4

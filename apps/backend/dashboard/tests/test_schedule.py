import logging
from datetime import UTC, datetime, timedelta
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client

from accounts.roles import Role
from bookings import checkin, holds, pricing, rules
from bookings.holds import Customer
from bookings.models import Booking, Court, SlotLock
from bookings.rules import Source, Status
from core import ratelimit
from dashboard import forms, queries, schedule, views
from dashboard.schedule import build_grid
from payments import confirm
from payments.confirm import confirm_payment
from payments.paymongo import CheckoutSession, Payment, PayMongoError

URL = "/dashboard/schedule/"
NEW = "/dashboard/schedule/new/"
HX = {"HX-Request": "true"}
# Monday 2 November 2026, 12:00 in Manila: hours 07-11 have ended, 12 is in progress.
NOW = datetime(2026, 11, 2, 12, tzinfo=rules.TIME_ZONE)
TODAY = NOW.date()
# Inside one 10-minute rate-limit window (04:00-04:09 UTC).
RATE_NOW = datetime(2026, 11, 2, 4, 1, tzinfo=UTC)
SESSION_ID = "cs_test_dash1"


def booking_url(reference: str) -> str:
    return f"/dashboard/schedule/booking/{reference}/"


def cancel_url(reference: str) -> str:
    return f"/dashboard/schedule/booking/{reference}/cancel/"


def check_in_url(reference: str) -> str:
    return f"/dashboard/desk/check-in/{reference}/"


def spend_viewer_budget() -> None:
    """Use up the viewer's write budget for the test client's address, as real writes would."""
    for _ in range(views.WRITE_LIMIT):
        ratelimit.hit(
            "staff_write",
            "127.0.0.1",
            limit=views.WRITE_LIMIT,
            window_seconds=views.WRITE_WINDOW_SECONDS,
        )


def court(code: str) -> Court:
    return Court.objects.get(code=code)


def make_user(role: Role) -> User:
    user, _ = User.objects.get_or_create(username=f"{role}@example.com")
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


def walk_in(
    code="mp-01", day=TODAY, hour=14, *, sport="badminton", name="", is_demo=False, now=NOW, hours=1
):
    return holds.create_staff_booking(
        source=Source.WALK_IN,
        court=court(code),
        sport=sport,
        coverage="full",
        half=None,
        day=day,
        start_hour=hour,
        hours=hours,
        created_by=None,
        customer_name=name,
        is_demo=is_demo,
        now=now,
    )


def basketball(code="bb-1", *, coverage="full", half=None, hour=14, hours=2, name="Juan Dela Cruz"):
    return holds.create_staff_booking(
        source=Source.WALK_IN,
        court=court(code),
        sport="basketball",
        coverage=coverage,
        half=half,
        day=TODAY,
        start_hour=hour,
        hours=hours,
        created_by=None,
        customer_name=name,
        now=NOW,
    )


def online(code="mp-01", day=TODAY, hour=14, *, is_demo=False, confirm=True) -> Booking:
    """A paid online booking, made the evening before through a real hold."""
    booking = holds.create_hold(
        court=court(code),
        sport="badminton",
        coverage="full",
        day=day,
        start_hour=hour,
        hours=1,
        customer=Customer(
            name="Maria Santos", email="maria.santos@example.com", mobile="+639000000001"
        ),
        now=datetime.combine(day - timedelta(days=1), datetime.min.time(), rules.TIME_ZONE)
        + timedelta(hours=20),
    )
    fields = {"is_demo": is_demo}
    if confirm:
        # Recorded as `payments.confirm._record` does; a demo payment has the seed's shape.
        payment_id = f"pay_{'demo' if is_demo else 'test'}_{booking.reference}"
        fields.update(
            status=Status.CONFIRMED, payment_id=payment_id, payment_method="card", paid_at=NOW
        )
    Booking.objects.filter(pk=booking.pk).update(**fields)
    booking.refresh_from_db()
    return booking


def checkout_hold(code="mp-04", hour=14) -> Booking:
    """A live online payment hold with a PayMongo checkout session, made ten minutes ago."""
    booking = holds.create_hold(
        court=court(code),
        sport="badminton",
        coverage="full",
        day=TODAY,
        start_hour=hour,
        hours=1,
        customer=Customer(
            name="Maria Santos", email="maria.santos@example.com", mobile="+639000000001"
        ),
        now=NOW - timedelta(minutes=10),
    )
    Booking.objects.filter(pk=booking.pk).update(checkout_session_id=SESSION_ID)
    booking.refresh_from_db()
    return booking


def paid_session(booking: Booking) -> CheckoutSession:
    """The hold's checkout session as PayMongo returns it once paid, within the hold."""
    payment = Payment(
        id="pay_test1",
        status="paid",
        amount_centavos=booking.price_centavos,
        currency="PHP",
        fee_centavos=1_250,
        net_centavos=booking.price_centavos - 1_250,
        method="gcash",
        paid_at=NOW - timedelta(minutes=5),
        livemode=False,
    )
    return CheckoutSession(
        id=SESSION_ID,
        checkout_url=f"https://checkout.paymongo.com/{SESSION_ID}",
        status="active",
        livemode=False,
        metadata={"booking_id": str(booking.id)},
        payments=(payment,),
    )


def mock_client(monkeypatch) -> MagicMock:
    """Replace `payments.confirm.get_client`, which `expire_session` calls, with a mock usable as
    `with get_client() as client:`."""
    factory = MagicMock(name="get_client")
    monkeypatch.setattr(confirm, "get_client", factory)
    return factory.return_value.__enter__.return_value


def form_data(**overrides):
    data = {
        "kind": "walk_in",
        "court": "mp-01",
        "date": TODAY.isoformat(),
        "sport": "badminton",
        "coverage": "full",
        "half": "",
        "start_hour": "15",
        "hours": "2",
        "customer_name": "Juan Dela Cruz",
        "note": "",
    }
    data.update(overrides)
    return data


@pytest.fixture(autouse=True)
def pinned_clock(monkeypatch):
    monkeypatch.setattr(views, "timezone", SimpleNamespace(now=lambda: NOW))
    monkeypatch.setattr(ratelimit, "timezone", SimpleNamespace(now=lambda: RATE_NOW))


@pytest.fixture
def owner(client):
    client.force_login(make_user(Role.OWNER))
    return client


@pytest.fixture
def viewer(client):
    client.force_login(make_user(Role.VIEWER))
    return client


class Html(HTMLParser):
    """Every start tag with its attributes."""

    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def with_class(html, name):
    """The attributes of every element carrying the class `name`, in document order."""
    return [attrs for _, attrs in Html(html).tags if name in attrs.get("class", "").split()]


def assert_csp_safe(html):
    tags = Html(html).tags
    assert [attrs for tag, attrs in tags if tag == "script" and "src" not in attrs] == []
    assert not [name for _, attrs in tags for name in attrs if name.startswith("hx-on")]
    assert not [attrs for _, attrs in tags if "style" in attrs]
    assert "javascript:" not in html


# --- access -------------------------------------------------------------------------------------


@pytest.mark.django_db
class TestAccess:
    @pytest.mark.parametrize("url", [URL, NEW, booking_url("ABC123")])
    def test_anonymous_is_redirected_to_login(self, client, url):
        response = client.get(url)

        assert response.status_code == 302
        assert response["Location"] == "/dashboard/login/"

    def test_htmx_anonymous_gets_hx_redirect(self, client):
        response = client.get(URL, headers=HX)

        assert response.status_code == 200
        assert response["HX-Redirect"] == "/dashboard/login/"
        assert response.content == b""

    def test_anonymous_writes_are_redirected_and_change_nothing(self, client):
        booking = walk_in()

        assert client.post(cancel_url(booking.reference)).status_code == 302
        assert client.post(NEW, form_data()).status_code == 302
        booking.refresh_from_db()
        assert booking.status == Status.CONFIRMED
        assert Booking.objects.count() == 1

    def test_schedule_is_in_the_sidebar_nav(self, owner):
        html = owner.get(URL).content.decode()

        assert '<aside class="dash-side"' in html
        assert '<a href="/dashboard/schedule/" aria-current="page">Schedule</a>' in html
        assert html.count('aria-current="page"') == 1
        assert html.index('<nav class="dash-nav"') < html.index(">Schedule</a>")
        assert '<div id="toast" class="toast" role="status" aria-live="polite"></div>' in html


# --- the grid -----------------------------------------------------------------------------------


@pytest.mark.django_db
class TestGrid:
    def test_20_rows_by_16_hours(self):
        # 18 courts + 2 extra rows: each of the 2 basketball courts is a Half A and a Half B row.
        # (The unit's prompt said 22, but 18 + 2 is 20: one row per lockable space.)
        grid = build_grid(TODAY, role=Role.OWNER, now=NOW)

        assert len(grid.rows) == 20 == queries.SPACE_COUNT
        assert all(sum(cell.colspan for cell in row.cells) == 16 for row in grid.rows)
        heads = grid.hour_heads
        assert (heads[0].label, heads[0].col) == ("7 AM", 2)
        assert (heads[-1].label, heads[-1].col, len(heads)) == ("10 PM", 17, 16)
        assert [row.label for row in grid.rows[:3]] == [
            "Basketball Court 1 · Half A",
            "Basketball Court 1 · Half B",
            "Basketball Court 2 · Half A",
        ]
        assert grid.rows[4].label == "Tennis Court 1"
        assert grid.rows[-1].label == "Court 12"

    def test_rows_sit_under_three_group_headings(self):
        grid = build_grid(TODAY, role=Role.OWNER, now=NOW)

        assert [(group.label, group.row) for group in grid.groups] == [
            ("Basketball · Volleyball", 2),
            ("Tennis", 7),
            ("Multi-courts · Badminton & Pickleball", 12),
        ]
        # Row 1 is the hour header; a heading row precedes each kind of court.
        assert [row.grid_row for row in grid.rows] == [*range(3, 7), *range(8, 12), *range(13, 25)]
        assert (grid.rows[0].name, grid.rows[0].half) == ("Basketball Court 1", "Half A")
        assert (grid.rows[4].name, grid.rows[4].half) == ("Tennis Court 1", "")

    def test_page_is_one_css_grid_of_20_court_rows(self, owner):
        html = owner.get(URL).content.decode()

        assert [attrs["class"] for attrs in with_class(html, "sg-group")] == [
            "sg-group r-2",
            "sg-group r-7",
            "sg-group r-12",
        ]
        assert len(with_class(html, "sg-court")) == 20
        assert len(with_class(html, "sg-hour")) == 16
        # Every hour of every row is either a free cell or part of a block: nothing is booked here.
        assert len(with_class(html, "sg-cell")) == 20 * 16
        assert with_class(html, "sg-block") == []
        assert "<table" not in html

    def test_the_page_has_one_h1_and_the_shell_heading(self, owner):
        html = owner.get(URL).content.decode()

        assert html.count("<h1") == 1
        assert '<h1 class="dash-heading">Schedule</h1>' in html

    def test_full_basketball_booking_appears_in_both_half_rows(self):
        booking = holds.create_staff_booking(
            source=Source.WALK_IN,
            court=court("bb-1"),
            sport="basketball",
            coverage="full",
            half=None,
            day=TODAY,
            start_hour=14,
            hours=2,
            created_by=None,
            customer_name="Juan Dela Cruz",
            now=NOW,
        )

        rows = build_grid(TODAY, role=Role.VIEWER, now=NOW).rows

        for row in rows[:2]:
            (segment,) = [cell for cell in row.cells if cell.reference]
            assert segment.reference == booking.reference
            assert (segment.hour, segment.colspan) == (14, 2)
            assert segment.source == Source.WALK_IN and segment.status == Status.CONFIRMED
            assert segment.name == "Juan D."
            assert segment.sport == "Basketball"
            assert segment.can_cancel
            assert segment.block_state == "walk_in"
        assert len(rows[0].cells) == 15

    def test_segments_carry_source_status_demo_and_permissions(self):
        paid = online("mp-01", hour=14)
        demo = online("mp-02", hour=14, is_demo=True)
        hold = online("mp-03", hour=15, confirm=False)
        Booking.objects.filter(pk=hold.pk).update(hold_expires_at=NOW + timedelta(minutes=10))
        blocked = holds.create_staff_booking(
            source=Source.BLOCK,
            court=court("tn-1"),
            sport=None,
            coverage="full",
            half=None,
            day=TODAY,
            start_hour=13,
            hours=3,
            created_by=None,
            note="Resurfacing",
            now=NOW,
        )

        grid = build_grid(TODAY, role=Role.VIEWER, now=NOW)
        cells = {cell.reference: cell for row in grid.rows for cell in row.cells if cell.reference}

        assert cells[paid.reference].block_state == "online"
        assert not cells[paid.reference].can_cancel  # A real visitor's online booking.
        assert cells[demo.reference].is_demo and cells[demo.reference].can_cancel
        assert cells[hold.reference].block_state == "pending"
        assert cells[hold.reference].status == Status.PENDING
        assert cells[blocked.reference].block_state == "block"
        assert cells[blocked.reference].colspan == 3
        assert cells[blocked.reference].text == "Resurfacing"
        owner_cells = {
            cell.reference: cell
            for row in build_grid(TODAY, role=Role.OWNER, now=NOW).rows
            for cell in row.cells
            if cell.reference
        }
        assert owner_cells[paid.reference].can_cancel

    def test_past_hours_today_offer_no_add(self, owner):
        cells = build_grid(TODAY, role=Role.OWNER, now=NOW).rows[4].cells

        assert [cell.past for cell in cells[:6]] == [True] * 5 + [False]
        assert not any(cell.addable for cell in cells[:5])
        assert all(cell.addable for cell in cells[5:])
        assert cells[5].label == "Tennis Court 1, 12 PM, free: add booking"

        html = owner.get(URL).content.decode()
        assert 'aria-label="Tennis Court 1, 11 AM, free: add booking"' not in html
        assert 'aria-label="Tennis Court 1, 6 PM, free: add booking"' in html
        assert "hour=18&amp;date=2026-11-02" in html

    def test_viewer_cannot_add_past_the_demo_window(self):
        too_far = TODAY + timedelta(days=7)

        assert any(c.addable for c in build_grid(too_far, role=Role.OWNER, now=NOW).rows[0].cells)
        assert not any(
            cell.addable
            for row in build_grid(too_far, role=Role.VIEWER, now=NOW).rows
            for cell in row.cells
        )
        last = TODAY + timedelta(days=6)
        assert all(c.addable for c in build_grid(last, role=Role.VIEWER, now=NOW).rows[0].cells)

    def test_htmx_get_returns_only_the_grid_partial(self, owner):
        response = owner.get(URL, {"date": "2026-11-03"}, headers=HX)
        html = response.content.decode()

        assert response.status_code == 200
        assert "<html" not in html and "<h1>" not in html and 'id="panel"' not in html
        assert 'class="sg"' in html
        assert "Tuesday 3 November 2026" in html
        assert 'hx-target="#grid"' in html and 'hx-push-url="true"' in html
        assert 'href="/dashboard/schedule/?date=2026-11-02"' in html  # Prev, with a real href.
        assert 'id="toast"' not in html
        assert "no-store" in response["Cache-Control"]

    def test_history_restore_gets_the_whole_page(self, owner):
        headers = {**HX, "HX-History-Restore-Request": "true"}

        assert "<html" in owner.get(URL, headers=headers).content.decode()

    @pytest.mark.parametrize(
        ("value", "shown"),
        [
            ("", "Monday 2 November 2026"),
            ("not-a-date", "Monday 2 November 2026"),
            ("2026-11-09", "Monday 9 November 2026"),
            ("2099-01-01", "Wednesday 2 December 2026"),  # Clamped to today + 30.
            ("2000-01-01", "Saturday 3 October 2026"),  # Clamped to today - 30.
        ],
    )
    def test_date_parameter(self, owner, value, shown):
        assert shown in owner.get(URL, {"date": value}).content.decode()

    def test_edges_of_the_range_have_no_prev_or_next(self):
        assert build_grid(TODAY + timedelta(days=30), role=Role.OWNER, now=NOW).next_day is None
        assert build_grid(TODAY - timedelta(days=30), role=Role.OWNER, now=NOW).prev_day is None

    def test_page_is_csp_safe_with_a_legend(self, viewer):
        walk_in(name="Juan Dela Cruz")
        response = viewer.get(URL)
        html = response.content.decode()

        assert "script-src 'self'" in response["Content-Security-Policy"]
        assert_csp_safe(html)
        assert html.count("hx-headers=") == 2
        assert '<aside id="panel" class="panel" aria-live="polite"' in html
        for state in ("online", "checked_in", "walk_in", "pending", "block", "done"):
            assert f"sg-swatch st-{state}" in html  # The legend.
        assert "sg-block st-walk_in" in html
        assert "Dela Cruz" not in html and "Juan D." in html

    def test_hx_config_swaps_refusals(self, owner):
        html = owner.get(URL).content.decode()

        assert '{"code":"403|429","swap":true,"error":false}' in html


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({}, "online"),
        ({"source": "walk_in"}, "walk_in"),
        ({"checked_in_at": NOW}, "checked_in"),
        ({"source": "walk_in", "checked_in_at": NOW}, "checked_in"),
        ({"ends_at": NOW - timedelta(hours=1)}, "done"),
        # Ended wins over checked in, and over the source.
        ({"source": "walk_in", "checked_in_at": NOW, "ends_at": NOW}, "done"),
        ({"status": "pending"}, "pending"),
        ({"source": "block"}, "block"),
        ({"source": "block", "ends_at": NOW - timedelta(hours=1)}, "block"),
    ],
)
def test_block_state_follows_status_key(fields, expected):
    booking = SimpleNamespace(
        **{
            "status": "confirmed",
            "source": "online",
            "ends_at": NOW + timedelta(hours=1),
            "checked_in_at": None,
            **fields,
        }
    )

    assert schedule.block_state(booking, NOW) == expected


def test_the_grid_line_classes_are_written_out_in_the_stylesheet():
    css = (Path(forms.__file__).parent / "static/dashboard/dashboard.css").read_text()
    wanted = (
        [f".r-{n}" for n in range(2, 27)]
        + [f".c-{n}" for n in range(2, 18)]
        + [f".rs-{n}" for n in range(1, 4)]
        + [f".cs-{n}" for n in range(1, 4)]
        + [f".now-m-{n}" for n in range(0, 60, 5)]
    )

    assert [name for name in wanted if f"{name} {{" not in css] == []
    # The last row any court can take, and the widest hour span, fit the generated classes.
    assert 2 + 3 + queries.SPACE_COUNT <= 26 and rules.MAX_HOURS <= 3


@pytest.mark.django_db
class TestBlocks:
    def test_a_full_basketball_booking_is_one_block_over_both_halves(self, owner):
        booking = basketball()

        (block,) = with_class(owner.get(URL).content.decode(), "sg-block")

        assert set(block["class"].split()) == {
            "sg-block",
            "st-walk_in",
            "r-3",
            "rs-2",
            "c-9",
            "cs-2",
        }
        assert block["hx-get"] == booking_url(booking.reference)
        assert block["hx-target"] == "#panel"
        # Over both halves it is the court's, not Half A's.
        assert (
            block["aria-label"]
            == "Basketball Court 1, 2 PM to 4 PM, walk-in, Juan Dela Cruz: details"
        )

    def test_a_half_booking_is_one_row(self, owner):
        booking = basketball("bb-2", coverage="half", half="B", hour=18, hours=1)

        html = owner.get(URL).content.decode()

        (block,) = with_class(html, "sg-block")
        assert set(block["class"].split()) == {
            "sg-block",
            "st-walk_in",
            "r-6",
            "rs-1",
            "c-13",
            "cs-1",
        }
        assert block["hx-get"] == booking_url(booking.reference)
        assert block["aria-label"].startswith("Basketball Court 2 · Half B, 6 PM to 7 PM")
        assert "Basketball · half · " + booking.reference in html

    def test_a_three_hour_booking_spans_three_columns(self, owner):
        walk_in("tn-1", hour=16, sport="tennis", hours=3)

        (block,) = with_class(owner.get(URL).content.decode(), "sg-block")

        assert {"r-8", "rs-1", "c-11", "cs-3"} <= set(block["class"].split())

    def test_every_booking_is_one_block_in_its_state(self):
        paid = online("mp-01", hour=8)  # Ended at 9: done.
        arrived = online("mp-02", hour=12)
        Booking.objects.filter(pk=arrived.pk).update(checked_in_at=NOW)
        coming = online("mp-03", hour=19)
        hold = online("mp-04", hour=15, confirm=False)
        Booking.objects.filter(pk=hold.pk).update(hold_expires_at=NOW + timedelta(minutes=10))
        cash = walk_in("mp-05")
        blocked = holds.create_staff_booking(
            source=Source.BLOCK,
            court=court("bb-1"),
            sport=None,
            coverage="full",
            half=None,
            day=TODAY,
            start_hour=13,
            hours=3,
            created_by=None,
            note="Resurfacing",
            now=NOW,
        )

        blocks = {b.reference: b for b in build_grid(TODAY, role=Role.OWNER, now=NOW).blocks}

        assert {ref: block.state for ref, block in blocks.items()} == {
            paid.reference: "done",
            arrived.reference: "checked_in",
            coming.reference: "online",
            hold.reference: "pending",
            cash.reference: "walk_in",
            blocked.reference: "block",
        }
        # A block over a basketball court holds both halves.
        assert (blocks[blocked.reference].row, blocks[blocked.reference].row_span) == (3, 2)
        assert blocks[blocked.reference].name == "Resurfacing"
        assert blocks[blocked.reference].sub == f"Blocked · {blocked.reference}"

    def test_names_are_masked_in_python_for_the_viewer(self):
        walk_in("mp-01", name="Juan Dela Cruz")
        walk_in("mp-02", hour=15)

        owner_names = {b.name for b in build_grid(TODAY, role=Role.OWNER, now=NOW).blocks}
        viewer_names = {b.name for b in build_grid(TODAY, role=Role.VIEWER, now=NOW).blocks}

        assert owner_names == {"Juan Dela Cruz", "Badminton"}
        assert viewer_names == {"Juan D.", "Badminton"}

    def test_free_cells_are_buttons_unless_past_or_out_of_range(self, owner):
        walk_in("tn-1", hour=18, sport="tennis")

        grid = build_grid(TODAY, role=Role.OWNER, now=NOW)
        cells = {(c.row, c.col): c for c in grid.empty_cells}

        assert len(cells) == 20 * 16 - 1
        assert (8, 13) not in cells  # Tennis Court 1 at 6 PM is booked.
        free = cells[(8, 12)]
        assert (free.court_code, free.space, free.hour) == ("tn-1", "F", 17)
        assert free.addable and not free.past
        assert free.label == "Tennis Court 1, 5 PM, free: add booking"
        assert cells[(8, 2)].past and not cells[(8, 2)].addable  # 7 AM has ended.

        html = owner.get(URL).content.decode()
        assert len(with_class(html, "sg-cell-past")) == 20 * 5  # 7 AM to 11 AM, every row.
        (button,) = [a for a in with_class(html, "sg-cell") if a.get("aria-label") == free.label]
        assert button["hx-get"] == (f"{NEW}?court=tn-1&space=F&hour=17&date={TODAY.isoformat()}")
        assert set(button["class"].split()) == {"sg-cell", "r-8", "c-12"}

    def test_the_viewer_gets_no_buttons_past_the_demo_window(self, viewer):
        far = (TODAY + timedelta(days=7)).isoformat()

        html = viewer.get(URL, {"date": far}).content.decode()

        assert len(with_class(html, "sg-cell")) == 20 * 16
        assert all("hx-get" not in a for a in with_class(html, "sg-cell"))


@pytest.mark.django_db
class TestNowMarker:
    def test_today_has_a_marker_in_the_current_hour(self, owner):
        html = owner.get(URL).content.decode()

        (marker,) = with_class(html, "sg-now")
        assert marker["class"] == "sg-now c-7"  # 12 PM: hour - 5.
        assert '<span class="sg-now-line now-m-0"></span>' in html
        assert '<span class="sg-now-chip now-m-0">12:00</span>' in html
        assert [a["class"] for a in with_class(html, "sg-hour-now")] == ["sg-hour c-7 sg-hour-now"]
        assert len(with_class(html, "sg-hour-past")) == 5  # 7 AM to 11 AM.
        assert_csp_safe(html)

    @pytest.mark.parametrize(
        ("minutes", "css", "label"),
        [
            (0, "now-m-0", "12:00"),
            (4, "now-m-0", "12:04"),
            (48, "now-m-45", "12:48"),
            (59, "now-m-55", "12:59"),
        ],
    )
    def test_the_marker_sits_in_five_minute_steps(self, minutes, css, label):
        grid = build_grid(TODAY, role=Role.OWNER, now=NOW + timedelta(minutes=minutes))

        assert (grid.now_col, grid.now_minute_class, grid.now_label) == (7, css, label)

    def test_no_marker_on_another_day(self, owner):
        for day in ("2026-11-03", "2026-11-01"):
            html = owner.get(URL, {"date": day}).content.decode()

            assert "sg-now" not in html and "sg-hour-now" not in html
        grid = build_grid(TODAY + timedelta(days=1), role=Role.OWNER, now=NOW)
        assert (grid.now_col, grid.now_minute_class, grid.now_label) == (None, "", "")

    def test_no_marker_while_the_venue_is_closed(self):
        for hour, minute in ((6, 30), (23, 15)):
            now = datetime(2026, 11, 2, hour, minute, tzinfo=rules.TIME_ZONE)

            assert build_grid(TODAY, role=Role.OWNER, now=now).now_col is None

    def test_a_past_day_has_every_hour_past_and_a_future_day_none(self):
        past = build_grid(TODAY - timedelta(days=1), role=Role.OWNER, now=NOW)
        future = build_grid(TODAY + timedelta(days=1), role=Role.OWNER, now=NOW)

        assert all(head.past for head in past.hour_heads)
        assert not any(head.past for head in future.hour_heads)


# --- side panel ---------------------------------------------------------------------------------


@pytest.mark.django_db
class TestPanel:
    def test_viewer_panel_is_masked_and_has_no_cancel_for_a_real_online_booking(self, viewer):
        booking = online()

        response = viewer.get(booking_url(booking.reference), headers=HX)
        html = response.content.decode()

        assert response.status_code == 200
        assert "<html" not in html
        assert booking.reference in html
        assert "Maria S." in html and "m•••@example.com" in html and "•••01" in html
        for secret in ("maria.santos", "639000000001", "Santos"):
            assert secret not in html
        assert "Cancel booking" not in html and "hx-post" not in html
        assert "PayMongo" not in html

    def test_owner_panel_is_raw_with_cancel_and_the_refund_note(self, owner):
        booking = online()

        html = owner.get(booking_url(booking.reference), headers=HX).content.decode()

        assert "maria.santos@example.com" in html and "+639000000001" in html
        assert f'hx-post="{cancel_url(booking.reference)}"' in html
        assert "hx-confirm=" in html
        assert "Refund it in the PayMongo dashboard (test mode)." in html
        assert_csp_safe(html)

    def test_owner_panel_has_no_refund_note_on_a_demo_online_booking(self, owner):
        booking = online(is_demo=True)

        html = owner.get(booking_url(booking.reference), headers=HX).content.decode()

        assert f'hx-post="{cancel_url(booking.reference)}"' in html
        assert "PayMongo" not in html
        assert not schedule.booking_detail(booking, role=Role.OWNER).refund_note

    def test_viewer_sees_cancel_for_demo_and_walk_in_bookings(self, viewer):
        for booking in (online(is_demo=True), walk_in("mp-02")):
            html = viewer.get(booking_url(booking.reference), headers=HX).content.decode()
            assert "Cancel booking" in html
            assert "PayMongo" not in html

    def test_walk_in_notes_are_owner_only(self, client):
        booking = holds.create_staff_booking(
            source=Source.WALK_IN,
            court=court("mp-01"),
            sport="badminton",
            coverage="full",
            half=None,
            day=TODAY,
            start_hour=14,
            hours=1,
            created_by=None,
            note="Paid by Juan's office",
            now=NOW,
        )
        client.force_login(make_user(Role.VIEWER))
        assert (
            "Juan&#x27;s office"
            not in client.get(booking_url(booking.reference), headers=HX).content.decode()
        )
        client.force_login(make_user(Role.OWNER))
        html = client.get(booking_url(booking.reference), headers=HX).content.decode()
        assert "Juan&#x27;s office" in html

    def test_unknown_reference_is_404(self, owner):
        assert owner.get(booking_url("NOPE12345")).status_code == 404
        assert owner.post(cancel_url("NOPE12345")).status_code == 404

    def test_panel_is_a_header_a_key_value_list_and_the_actions(self, owner):
        booking = walk_in(name="Juan Dela Cruz")

        html = owner.get(booking_url(booking.reference), headers=HX).content.decode()

        assert '<h2 class="sp-title">Booking</h2>' in html
        assert f'<span class="desk-ref">{booking.reference}</span>' in html
        assert '<span class="pill pill-confirmed">Confirmed</span>' in html
        assert '<p class="sp-name">Juan Dela Cruz</p>' in html
        assert "<dt>Court</dt><dd>Court 1</dd>" in html
        assert "<dt>Source</dt><dd>Walk-in</dd>" in html
        assert "Checked in</dt>" not in html
        assert "<h1" not in html
        assert_csp_safe(html)

    def test_check_in_is_a_post_to_the_desks_endpoint_returning_to_the_schedule(self, owner):
        booking = walk_in(name="Juan Dela Cruz")

        html = owner.get(booking_url(booking.reference), headers=HX).content.decode()

        (form,) = with_class(html, "sp-action")
        assert form["hx-post"] == check_in_url(booking.reference)
        assert form["action"] == check_in_url(booking.reference) and form["method"] == "post"
        assert form["hx-target"] == "#grid"
        assert '<input type="hidden" name="return" value="schedule">' in html
        assert 'name="csrfmiddlewaretoken"' in html
        assert ">Check in</button>" in html
        assert "Cancel booking" in html  # Still offered.

    def test_viewer_has_no_check_in_for_a_real_online_booking(self, viewer):
        booking = online()

        html = viewer.get(booking_url(booking.reference), headers=HX).content.decode()

        assert "Check in" not in html and check_in_url(booking.reference) not in html

    def test_viewer_has_check_in_for_demo_and_walk_in_bookings(self, viewer):
        for booking in (online(is_demo=True), walk_in("mp-02")):
            html = viewer.get(booking_url(booking.reference), headers=HX).content.decode()
            assert check_in_url(booking.reference) in html

    def test_no_check_in_once_checked_in_ended_or_for_a_block(self, owner):
        arrived = walk_in("mp-01")
        Booking.objects.filter(pk=arrived.pk).update(checked_in_at=NOW)
        ended = online("mp-02", hour=8)
        blocked = holds.create_staff_booking(
            source=Source.BLOCK,
            court=court("tn-1"),
            sport=None,
            coverage="full",
            half=None,
            day=TODAY,
            start_hour=13,
            hours=1,
            created_by=None,
            note="Maintenance",
            now=NOW,
        )

        for booking in (arrived, ended, blocked):
            html = owner.get(booking_url(booking.reference), headers=HX).content.decode()
            assert check_in_url(booking.reference) not in html

        arrived_html = owner.get(booking_url(arrived.reference), headers=HX).content.decode()
        assert "pill-checked_in" in arrived_html and "Checked in</dt><dd>12:00 PM" in arrived_html
        assert (
            "pill-completed" in owner.get(booking_url(ended.reference), headers=HX).content.decode()
        )

    def test_detail_can_check_in_follows_the_role_permission(self):
        today = walk_in("mp-01")
        tomorrow = walk_in("mp-02", day=TODAY + timedelta(days=1))
        real = online("mp-03")

        assert schedule.booking_detail(today, role=Role.OWNER, now=NOW).can_check_in
        assert not schedule.booking_detail(tomorrow, role=Role.OWNER, now=NOW).can_check_in
        assert schedule.booking_detail(real, role=Role.OWNER, now=NOW).can_check_in
        assert not schedule.booking_detail(real, role=Role.VIEWER, now=NOW).can_check_in
        assert schedule.booking_detail(today, role=Role.VIEWER, now=NOW).can_check_in
        detail = schedule.booking_detail(today, role=Role.OWNER, now=NOW)
        assert (detail.status, detail.status_key, detail.checked_in_clock) == (
            "Confirmed",
            "confirmed",
            "",
        )


# --- cancel -------------------------------------------------------------------------------------


@pytest.mark.django_db
class TestCancel:
    def test_viewer_cannot_cancel_a_real_online_booking(self, viewer):
        booking = online()

        response = viewer.post(cancel_url(booking.reference), headers=HX)

        assert response.status_code == 403
        assert "You can&#x27;t cancel this booking." in response.content.decode()
        assert response["HX-Retarget"] == "#panel"
        booking.refresh_from_db()
        assert booking.status == Status.CONFIRMED and booking.cancelled_at is None
        assert SlotLock.objects.filter(booking=booking).count() == 1

    def test_viewer_can_cancel_a_demo_booking(self, viewer):
        booking = online(is_demo=True)

        response = viewer.post(cancel_url(booking.reference), headers=HX)

        assert response.status_code == 200
        booking.refresh_from_db()
        assert booking.status == Status.CANCELLED
        assert not SlotLock.objects.filter(booking=booking).exists()

    def test_owner_cancels_an_online_booking_and_gets_the_grid_and_a_toast(self, owner, caplog):
        booking = online()

        with caplog.at_level(logging.INFO, logger="cb.bookings"):
            response = owner.post(cancel_url(booking.reference), headers=HX)
        html = response.content.decode()

        assert response.status_code == 200
        booking.refresh_from_db()
        # It was paid, so it is freed as needing a refund.
        assert booking.status == Status.NEEDS_REFUND and booking.cancelled_at == NOW
        assert not SlotLock.objects.filter(booking=booking).exists()
        assert "<html" not in html and 'class="sg"' in html
        assert booking.reference not in html  # The freed slot is free on the refreshed grid.
        toast = next(a for t, a in Html(html).tags if t == "div" and a.get("id") == "toast")
        assert toast["hx-swap-oob"] == "true" and toast["role"] == "status"
        assert (
            "Booking cancelled. It was paid: refund it in the PayMongo dashboard (test mode).</div>"
            in html
        )
        assert "HX-Trigger" not in response
        assert (
            f"booking.cancelled ref={booking.reference} role=owner status=needs_refund"
            in caplog.text
        )
        assert "Maria" not in caplog.text and "maria" not in caplog.text

    def test_owner_cancelling_a_paid_online_booking_leaves_it_needing_a_refund(self, owner):
        booking = checkout_hold()
        assert confirm_payment(paid_session(booking), now=NOW).status == Status.CONFIRMED

        response = owner.post(cancel_url(booking.reference), headers=HX)

        assert response.status_code == 200
        assert (
            "Booking cancelled. It was paid: refund it in the PayMongo dashboard (test mode)."
            in response.content.decode()
        )
        booking.refresh_from_db()
        assert booking.status == Status.NEEDS_REFUND and booking.cancelled_at == NOW
        assert booking.payment_id == "pay_test1"
        assert not SlotLock.objects.filter(booking=booking).exists()
        assert queries.overview(role=Role.OWNER, now=NOW).alerts.needs_refund == 1
        # A webhook redelivery or a revisit of the success page changes nothing.
        updated_at = booking.updated_at
        result = confirm_payment(paid_session(booking), now=NOW)
        booking.refresh_from_db()
        assert result.status == Status.NEEDS_REFUND
        assert booking.status == Status.NEEDS_REFUND and booking.updated_at == updated_at

    def test_cancelling_a_pending_hold_expires_its_checkout_session_after_commit(
        self, owner, monkeypatch, django_capture_on_commit_callbacks
    ):
        client = mock_client(monkeypatch)
        booking = checkout_hold()

        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            response = owner.post(cancel_url(booking.reference), headers=HX)
            client.expire_checkout_session.assert_not_called()

        assert response.status_code == 200
        assert "Booking cancelled.</div>" in response.content.decode()
        assert len(callbacks) == 1
        client.expire_checkout_session.assert_called_once_with(SESSION_ID)
        booking.refresh_from_db()
        assert booking.status == Status.CANCELLED
        assert not SlotLock.objects.filter(booking=booking).exists()

    def test_a_failed_expiry_is_logged_and_never_raised(
        self, owner, monkeypatch, django_capture_on_commit_callbacks, caplog
    ):
        client = mock_client(monkeypatch)
        client.expire_checkout_session.side_effect = PayMongoError("failed", status=500)
        booking = checkout_hold()

        with (
            caplog.at_level(logging.ERROR, logger="cb.payments"),
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = owner.post(cancel_url(booking.reference), {"return": "detail"})

        assert response.status_code == 303
        booking.refresh_from_db()
        assert booking.status == Status.CANCELLED
        assert f"payment.expire_failed session={SESSION_ID}" in caplog.text
        assert "Maria" not in caplog.text and "maria" not in caplog.text

    def test_a_confirmed_booking_has_no_session_to_expire(
        self, owner, monkeypatch, django_capture_on_commit_callbacks
    ):
        client = mock_client(monkeypatch)
        booking = checkout_hold()
        confirm_payment(paid_session(booking), now=NOW)

        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            owner.post(cancel_url(booking.reference), headers=HX)

        assert callbacks == []
        client.expire_checkout_session.assert_not_called()

    def test_an_unpaid_walk_in_is_just_cancelled(self, owner):
        booking = walk_in()

        response = owner.post(cancel_url(booking.reference), headers=HX)

        assert "Booking cancelled.</div>" in response.content.decode()
        booking.refresh_from_db()
        assert booking.status == Status.CANCELLED and booking.cancelled_at == NOW

    def test_a_demo_online_booking_is_just_cancelled(self, viewer):
        # Seeded demo payments are fictional (`pay_demo_…`) and have no checkout session.
        booking = online(is_demo=True)
        Booking.objects.filter(pk=booking.pk).update(payment_id="pay_demo_0001")

        response = viewer.post(cancel_url(booking.reference), headers=HX)

        assert "Booking cancelled.</div>" in response.content.decode()
        booking.refresh_from_db()
        assert booking.status == Status.CANCELLED

    def test_the_owner_just_cancels_a_demo_online_booking(self, owner):
        booking = online(is_demo=True)

        response = owner.post(cancel_url(booking.reference), headers=HX)

        assert "Booking cancelled.</div>" in response.content.decode()
        booking.refresh_from_db()
        assert booking.status == Status.CANCELLED and booking.cancelled_at == NOW
        assert booking.payment_id.startswith("pay_demo_")

    def test_cancelling_twice_is_refused(self, owner):
        booking = walk_in()
        owner.post(cancel_url(booking.reference))

        assert owner.post(cancel_url(booking.reference)).status_code == 403

    def test_get_is_not_allowed(self, owner):
        assert owner.get(cancel_url(walk_in().reference)).status_code == 405

    def test_viewer_cannot_cancel_a_walk_in_that_has_ended(self, viewer):
        # 10:00-11:00, made at 09:00, so it ended before NOW (12:00).
        booking = walk_in(hour=10, now=NOW - timedelta(hours=3))

        html = viewer.get(booking_url(booking.reference), headers=HX).content.decode()
        response = viewer.post(cancel_url(booking.reference), headers=HX)

        assert "Cancel booking" not in html and "hx-post" not in html
        assert response.status_code == 403
        assert "You can&#x27;t cancel this booking." in response.content.decode()
        booking.refresh_from_db()
        assert booking.status == Status.CONFIRMED and booking.cancelled_at is None
        assert SlotLock.objects.filter(booking=booking).count() == 1

    def test_owner_can_cancel_a_walk_in_that_has_ended(self, owner):
        booking = walk_in(hour=10, now=NOW - timedelta(hours=3))

        response = owner.post(cancel_url(booking.reference), headers=HX)

        assert response.status_code == 200
        booking.refresh_from_db()
        assert booking.status == Status.CANCELLED and booking.cancelled_at == NOW


def test_cancel_booking_wraps_release(db, caplog):
    booking = walk_in()

    with caplog.at_level(logging.INFO, logger="cb.bookings"):
        assert holds.cancel_booking(booking, by_role=Role.VIEWER, now=NOW) == Status.CANCELLED
        assert holds.cancel_booking(booking, by_role=Role.VIEWER, now=NOW) is None

    assert booking.status == Status.CANCELLED
    assert caplog.text.count("booking.cancelled") == 1
    assert f"booking.cancelled ref={booking.reference} role=viewer status=cancelled" in caplog.text


def test_cancel_booking_judges_the_locked_row(db):
    """A hold confirmed after the caller read it is cancelled as paid, not as a plain hold."""
    booking = checkout_hold()
    stale = Booking.objects.get(pk=booking.pk)
    confirm_payment(paid_session(booking), now=NOW)

    assert stale.status == Status.PENDING
    assert holds.cancel_booking(stale, by_role=Role.OWNER, now=NOW) == Status.NEEDS_REFUND
    assert (stale.status, stale.cancelled_at) == (Status.NEEDS_REFUND, NOW)


# --- create -------------------------------------------------------------------------------------


@pytest.mark.django_db
class TestPanelCheckIn:
    def test_owner_checks_in_and_the_grid_refreshes_with_a_toast(self, owner):
        booking = walk_in(name="Juan Dela Cruz")

        response = owner.post(check_in_url(booking.reference), {"return": "schedule"}, headers=HX)
        html = response.content.decode()

        assert response.status_code == 200
        assert "<html" not in html and 'class="sg"' in html
        assert "no-store" in response["Cache-Control"]
        assert (
            '<div id="toast" class="toast" role="status" aria-live="polite" hx-swap-oob="true">'
            '<span aria-hidden="true">✓ </span>Juan Dela Cruz checked in · Court 1</div>'
        ) in html
        assert (
            '<aside id="panel" class="panel" aria-live="polite" aria-label="Booking" hx-swap-oob'
            in html
        )
        (block,) = with_class(html, "sg-block")
        assert "st-checked_in" in block["class"].split()
        booking.refresh_from_db()
        assert booking.checked_in_at == NOW
        assert booking.checked_in_by == make_user(Role.OWNER)
        assert_csp_safe(html)

    def test_the_toast_is_masked_for_the_viewer_and_names_the_court(self, viewer):
        booking = walk_in("tn-2", sport="tennis", name="Juan Dela Cruz")

        response = viewer.post(check_in_url(booking.reference), {"return": "schedule"}, headers=HX)

        html = response.content.decode()
        assert "Juan D. checked in · Tennis Court 2</div>" in html
        assert "Dela Cruz" not in html
        assert_csp_safe(html)

    def test_the_toast_falls_back_to_the_reference_without_a_name(self, owner):
        booking = walk_in()

        html = owner.post(
            check_in_url(booking.reference), {"return": "schedule"}, headers=HX
        ).content.decode()

        assert f"{booking.reference} checked in · Court 1</div>" in html

    def test_without_htmx_it_redirects_to_the_bookings_day(self, owner):
        booking = walk_in()

        response = owner.post(check_in_url(booking.reference), {"return": "schedule"})

        assert response.status_code == 303
        assert response["Location"] == f"/dashboard/schedule/?date={TODAY.isoformat()}"
        booking.refresh_from_db()
        assert booking.checked_in_at == NOW

    def test_checking_in_twice_is_a_no_op_success(self, owner):
        booking = walk_in(name="Juan Dela Cruz")
        earlier = NOW - timedelta(minutes=5)
        Booking.objects.filter(pk=booking.pk).update(checked_in_at=earlier)

        response = owner.post(check_in_url(booking.reference), {"return": "schedule"}, headers=HX)

        assert response.status_code == 200
        assert "Juan Dela Cruz checked in · Court 1" in response.content.decode()
        booking.refresh_from_db()
        assert booking.checked_in_at == earlier and booking.checked_in_by is None

    def test_return_detail_goes_back_to_the_detail_page(self, owner):
        booking = walk_in()

        response = owner.post(check_in_url(booking.reference), {"return": "detail"}, headers=HX)

        assert response.status_code == 200 and response.content == b""
        assert response["HX-Redirect"] == f"/dashboard/bookings/{booking.reference}/"
        booking.refresh_from_db()
        assert booking.checked_in_at == NOW

    def test_return_detail_without_htmx_is_a_303(self, owner):
        booking = walk_in()

        response = owner.post(check_in_url(booking.reference), {"return": "detail"})

        assert response.status_code == 303
        assert response["Location"] == f"/dashboard/bookings/{booking.reference}/"
        booking.refresh_from_db()
        assert booking.checked_in_at == NOW

    @pytest.mark.parametrize("return_to", ["schedule", "detail"])
    def test_viewer_cannot_check_in_a_real_online_booking(self, viewer, return_to):
        booking = online()

        response = viewer.post(check_in_url(booking.reference), {"return": return_to}, headers=HX)
        html = response.content.decode()

        assert response.status_code == 403
        assert escape(views.CANT_CHECK_IN) in html
        assert response["HX-Retarget"] == "#panel" and response["HX-Reswap"] == "innerHTML"
        assert "<html" not in html and 'id="desk"' not in html
        assert_csp_safe(html)
        booking.refresh_from_db()
        assert booking.checked_in_at is None

    @pytest.mark.parametrize("return_to", ["schedule", "detail"])
    def test_the_viewer_budget_refuses_with_429_in_the_panel(self, viewer, return_to):
        booking = walk_in()
        spend_viewer_budget()

        response = viewer.post(check_in_url(booking.reference), {"return": return_to}, headers=HX)

        assert response.status_code == 429
        assert views.DEMO_LIMIT in response.content.decode()
        assert response["HX-Retarget"] == "#panel"
        booking.refresh_from_db()
        assert booking.checked_in_at is None

    @pytest.mark.parametrize(
        ("code", "message"),
        [
            ("not_confirmed", views.CHECK_IN_ERRORS["not_confirmed"]),
            ("ended", views.CHECK_IN_ERRORS["ended"]),
            ("something_else", views.CANT_CHECK_IN),
        ],
    )
    def test_a_check_in_error_is_shown_in_the_panel(self, owner, monkeypatch, code, message):
        booking = walk_in()

        def refuse(*args, **kwargs):
            raise checkin.CheckInError(code)

        monkeypatch.setattr(checkin, "check_in", refuse)

        response = owner.post(check_in_url(booking.reference), {"return": "schedule"}, headers=HX)

        assert response.status_code == 403
        assert escape(message) in response.content.decode()
        assert response["HX-Retarget"] == "#panel"

    def test_a_refusal_without_htmx_is_a_full_page(self, viewer):
        booking = online()

        response = viewer.post(check_in_url(booking.reference), {"return": "schedule"})
        html = response.content.decode()

        assert response.status_code == 403
        assert BANNER in html and "<html" in html and html.count("<h1") == 1
        assert escape(views.CANT_CHECK_IN) in html

    def test_without_a_known_return_the_desk_still_answers(self, viewer):
        booking = online()

        for data in ({}, {"return": "elsewhere"}):
            response = viewer.post(check_in_url(booking.reference), data, headers=HX)

            assert response.status_code == 403
            assert response["HX-Retarget"] == "#desk"

    def test_anonymous_cannot_check_in_from_the_panel(self, client):
        booking = walk_in()

        response = client.post(check_in_url(booking.reference), {"return": "schedule"})

        assert response.status_code == 302
        booking.refresh_from_db()
        assert booking.checked_in_at is None

    def test_unknown_reference_is_a_404(self, owner):
        assert owner.post(check_in_url("KC-ZZZZZZ"), {"return": "schedule"}).status_code == 404


@pytest.mark.django_db
class TestNewPanel:
    def test_prefills_the_clicked_cell(self, viewer):
        response = viewer.get(
            NEW, {"court": "bb-2", "space": "B", "hour": "18", "date": "2026-11-03"}, headers=HX
        )
        html = response.content.decode()

        assert response.status_code == 200
        assert "<html" not in html
        assert "Add to Basketball Court 2" in html
        assert 'name="court" value="bb-2"' in html
        assert 'name="date" value="2026-11-03"' in html
        assert '<option value="B" selected>Half B</option>' in html
        assert '<option value="half" selected>Half court</option>' in html
        assert '<option value="18" selected>6 PM</option>' in html
        assert 'value="tennis"' not in html  # Only the court's sports.
        assert 'hx-post="/dashboard/schedule/new/"' in html
        assert_csp_safe(html)

    def test_the_note_is_a_reason_list_for_the_viewer(self, viewer):
        html = viewer.get(
            NEW, {"court": "tn-1", "space": "F", "hour": "9"}, headers=HX
        ).content.decode()

        assert '<select name="note"' in html
        for reason in forms.BLOCK_REASONS:
            assert f'<option value="{reason}"' in html

    def test_the_note_is_free_text_for_the_owner(self, owner):
        html = owner.get(
            NEW, {"court": "tn-1", "space": "F", "hour": "9"}, headers=HX
        ).content.decode()

        assert '<input type="text" name="note"' in html and '<select name="note"' not in html

    def test_the_type_is_a_segmented_control_and_the_form_is_restyled(self, owner):
        html = owner.get(
            NEW, {"court": "tn-1", "space": "F", "hour": "9"}, headers=HX
        ).content.decode()

        assert html.count('<div class="seg">') == 1
        assert '<label><input type="radio" name="kind" value="walk_in"' in html
        assert 'value="walk_in" id="id_kind_0" required checked>Walk-in</label>' in html
        assert 'name="kind" value="block"' in html
        assert "A block (maintenance, an event) takes the whole court and needs a note." in html
        assert 'class="btn btn-dark sf-submit"' in html
        assert [a["class"] for a in with_class(html, "field")] == [
            "field sf-sport",
            "field sf-start_hour",
            "field sf-hours",
            "field sf-customer_name",
            "field sf-note",
        ]
        assert "<h1" not in html
        assert_csp_safe(html)

    def test_non_basketball_has_no_half_fields(self, owner):
        html = owner.get(
            NEW, {"court": "tn-1", "space": "F", "hour": "9"}, headers=HX
        ).content.decode()

        assert 'name="half"' not in html and 'name="coverage"' not in html
        assert '<option value="tennis" selected>Tennis</option>' in html

    @pytest.mark.parametrize("params", [{"court": "zz-9", "hour": "9"}, {"court": "tn-1"}])
    def test_bad_cell_is_404(self, owner, params):
        assert owner.get(NEW, params, headers=HX).status_code == 404


@pytest.mark.django_db
class TestCreate:
    def test_walk_in_is_confirmed_cash_and_priced_by_the_quote(self, owner):
        response = owner.post(NEW, form_data(), headers=HX)
        html = response.content.decode()

        assert response.status_code == 200
        booking = Booking.objects.get()
        assert booking.source == Source.WALK_IN
        assert booking.status == Status.CONFIRMED
        assert booking.payment_method == "cash"
        assert booking.price_centavos == pricing.quote("badminton", "full", TODAY, 15, 2)
        assert booking.created_by == User.objects.get(username="owner@example.com")
        assert booking.customer_name == "Juan Dela Cruz"
        assert not booking.is_demo
        assert SlotLock.objects.filter(booking=booking).count() == 2
        assert 'class="sg"' in html and booking.reference in html
        assert "Booking added." in html

    def test_second_walk_in_on_the_same_cell_is_just_taken(self, owner):
        owner.post(NEW, form_data())

        response = owner.post(NEW, form_data(start_hour="16", hours="1"), headers=HX)

        assert response.status_code == 200
        assert forms.SLOT_TAKEN in response.content.decode()
        assert response["HX-Retarget"] == "#panel"
        assert Booking.objects.count() == 1

    def test_a_block_requires_a_note(self, owner):
        response = owner.post(NEW, form_data(kind="block", note="  "))

        assert "A block needs a note" in response.content.decode()
        assert not Booking.objects.exists()

    def test_the_viewer_cannot_type_a_block_note(self, viewer):
        response = viewer.post(NEW, form_data(kind="block", note="Spray paint"), headers=HX)

        assert "Select a valid choice" in response.content.decode()
        assert not Booking.objects.exists()

    def test_the_viewer_can_block_with_a_listed_reason(self, viewer):
        response = viewer.post(NEW, form_data(kind="block", note="Maintenance"), headers=HX)

        assert "Booking added." in response.content.decode()
        assert Booking.objects.get().note == "Maintenance"

    def test_the_owner_can_still_type_a_block_note(self, owner):
        owner.post(NEW, form_data(kind="block", note="Spray paint"), headers=HX)

        assert Booking.objects.get().note == "Spray paint"

    def test_every_demo_block_note_is_a_listed_reason(self):
        from bookings import demo

        assert {n for n, *_ in demo.BLOCKS} <= set(forms.BLOCK_REASONS)

    def test_a_block_on_basketball_fills_both_halves(self, owner):
        data = form_data(kind="block", court="bb-1", sport="", note="League night", hours="3")

        assert owner.post(NEW, data, headers=HX).status_code == 200

        booking = Booking.objects.get()
        assert (booking.source, booking.sport, booking.price_centavos) == ("block", None, 0)
        assert booking.customer_name == ""  # A block has no customer.
        assert sorted(SlotLock.objects.values_list("space", flat=True)) == ["A"] * 3 + ["B"] * 3
        rows = build_grid(TODAY, role=Role.OWNER, now=NOW).rows[:2]
        assert all(any(cell.reference == booking.reference for cell in row.cells) for row in rows)

    def test_half_court_walk_in_takes_one_half(self, owner):
        data = form_data(court="bb-1", sport="basketball", coverage="half", half="B")

        owner.post(NEW, data)

        assert list(SlotLock.objects.values_list("space", flat=True).distinct()) == ["B"]

    def test_volleyball_is_forced_to_full_court(self, owner):
        data = form_data(court="bb-1", sport="volleyball", coverage="half", half="A")

        owner.post(NEW, data)

        booking = Booking.objects.get()
        assert (booking.coverage, booking.half) == ("full", None)

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"sport": "tennis"}, "That sport isn&#x27;t played on this court."),
            ({"sport": ""}, "Pick a sport for the walk-in."),
            ({"start_hour": "22", "hours": "2"}, "A booking has to end by closing time"),
            ({"start_hour": "9"}, "That time has already passed."),
            (
                {"court": "bb-1", "sport": "basketball", "coverage": "half"},
                "Pick Half A or Half B.",
            ),
            ({"customer_name": "x" * 81}, "at most 80 characters"),
        ],
    )
    def test_invalid_requests_show_a_form_error(self, owner, overrides, message):
        response = owner.post(NEW, form_data(**overrides), headers=HX)

        assert response.status_code == 200
        assert message in response.content.decode()
        assert not Booking.objects.exists()

    def test_viewer_bookings_are_demo_data(self, viewer):
        viewer.post(NEW, form_data())

        booking = Booking.objects.get()
        assert booking.is_demo
        assert booking.created_by == User.objects.get(username="viewer@example.com")

    def test_viewer_walk_in_past_the_demo_window_is_refused(self, viewer):
        late = (TODAY + timedelta(days=7)).isoformat()

        response = viewer.post(NEW, form_data(date=late))

        assert forms.DEMO_WINDOW in response.content.decode()
        assert forms.DEMO_WINDOW == "The demo takes bookings up to 6 days ahead."
        assert not Booking.objects.exists()
        viewer.post(NEW, form_data(date=(TODAY + timedelta(days=6)).isoformat()))
        assert Booking.objects.count() == 1

    def test_owner_has_no_demo_window(self, owner):
        owner.post(NEW, form_data(date=(TODAY + timedelta(days=7)).isoformat()))

        assert not Booking.objects.get().is_demo


# --- CSRF and the demo write limit --------------------------------------------------------------


@pytest.mark.django_db
class TestCsrf:
    def test_post_without_csrf_is_refused(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(make_user(Role.OWNER))
        booking = walk_in("mp-02")

        assert strict.post(NEW, form_data(), headers=HX).status_code == 403
        assert strict.post(cancel_url(booking.reference), headers=HX).status_code == 403
        booking.refresh_from_db()
        assert booking.status == Status.CONFIRMED
        assert Booking.objects.count() == 1

    def test_post_with_the_header_token_is_accepted(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(make_user(Role.OWNER))
        strict.get(URL)  # Sets the CSRF cookie, as the page does for htmx.
        token = strict.cookies["csrftoken"].value

        response = strict.post(NEW, form_data(), headers={**HX, "X-CSRFToken": token})

        assert response.status_code == 200
        assert Booking.objects.count() == 1


@pytest.mark.django_db
class TestWriteLimit:
    def _cells(self):
        for code in [f"mp-{n:02d}" for n in range(1, 13)]:
            for hour in (13, 15):
                yield {"court": code, "start_hour": str(hour), "hours": "1"}

    def test_viewer_21st_write_in_ten_minutes_is_refused(self, viewer):
        cells = self._cells()
        for _ in range(19):
            assert viewer.post(NEW, form_data(**next(cells)), headers=HX).status_code == 200
        demo = Booking.objects.filter(is_demo=True).first()
        assert (
            viewer.post(cancel_url(demo.reference), headers=HX).status_code == 200
        )  # The 20th write.

        create = viewer.post(NEW, form_data(**next(cells)), headers=HX)
        cancel = viewer.post(
            cancel_url(Booking.objects.filter(status="confirmed")[0].reference), headers=HX
        )

        assert create.status_code == 429 and cancel.status_code == 429
        assert "Demo limit reached. Try again in a few minutes." in create.content.decode()
        assert create["HX-Retarget"] == "#panel"
        assert Booking.objects.count() == 19
        assert Booking.objects.filter(status=Status.CANCELLED).count() == 1

    def test_the_owner_is_not_limited(self, owner):
        cells = self._cells()
        for _ in range(21):
            assert owner.post(NEW, form_data(**next(cells)), headers=HX).status_code == 200

        assert Booking.objects.count() == 21


@pytest.mark.django_db
class TestNulBytes:
    def test_a_nul_in_a_reference_is_a_404(self, owner):
        assert owner.get(booking_url("KC-%00AAAA"), headers=HX).status_code == 404
        assert owner.post(cancel_url("KC-%00AAAA"), headers=HX).status_code == 404

    def test_a_nul_in_the_court_is_a_404(self, owner):
        response = owner.get(
            f"{NEW}?court=%00&space=F&hour=10&date={TODAY.isoformat()}", headers=HX
        )

        assert response.status_code == 404


@pytest.mark.django_db
class TestInvalidWritesAreNotCharged:
    def test_invalid_viewer_posts_leave_the_budget_alone(self, viewer):
        for _ in range(views.WRITE_LIMIT + 1):
            response = viewer.post(NEW, form_data(kind="block", note=""), headers=HX)
            assert response.status_code == 200
            assert "A block needs a note" in response.content.decode()

        response = viewer.post(NEW, form_data(), headers=HX)

        assert response.status_code == 200
        assert "Booking added." in response.content.decode()


@pytest.mark.django_db
class TestDemoLiveCap:
    TOMORROW = TODAY + timedelta(days=1)

    def _viewer_bookings(self, count: int) -> None:
        """`count` live demo walk-ins made by the viewer, straight through `bookings.holds`."""
        user = make_user(Role.VIEWER)
        cells = [(f"mp-{n:02d}", hour) for n in range(1, 13) for hour in range(7, 12)]
        for code, hour in cells[:count]:
            holds.create_staff_booking(
                source=Source.WALK_IN,
                court=court(code),
                sport="badminton",
                coverage="full",
                half=None,
                day=self.TOMORROW,
                start_hour=hour,
                hours=1,
                created_by=user,
                is_demo=True,
                now=NOW,
            )

    def test_the_viewers_create_past_the_cap_is_refused(self, viewer):
        self._viewer_bookings(views.DEMO_LIVE_CAP)

        response = viewer.post(NEW, form_data(), headers=HX)

        assert response.status_code == 429
        assert (
            "The demo has enough bookings for now. Try cancelling one of yours, or come back "
            "tomorrow." in response.content.decode()
        )
        assert response["HX-Retarget"] == "#panel"
        assert Booking.objects.count() == views.DEMO_LIVE_CAP

    def test_the_owner_is_never_capped(self, owner):
        self._viewer_bookings(views.DEMO_LIVE_CAP)

        assert "Booking added." in owner.post(NEW, form_data(), headers=HX).content.decode()
        assert Booking.objects.count() == views.DEMO_LIVE_CAP + 1

    def test_past_and_cancelled_bookings_do_not_count(self, viewer):
        self._viewer_bookings(views.DEMO_LIVE_CAP - 1)
        user = make_user(Role.VIEWER)
        ended = holds.create_staff_booking(
            source=Source.WALK_IN,
            court=court("tn-1"),
            sport="tennis",
            coverage="full",
            half=None,
            day=TODAY,
            start_hour=9,
            hours=1,
            created_by=user,
            is_demo=True,
            now=NOW - timedelta(days=1),
        )
        cancelled = walk_in("mp-12", is_demo=True)
        Booking.objects.filter(pk=cancelled.pk).update(created_by=user)
        holds.cancel_booking(cancelled, by_role=Role.VIEWER, now=NOW)
        assert ended.ends_at <= NOW
        assert schedule.viewer_live_bookings(user, NOW) == views.DEMO_LIVE_CAP - 1

        assert "Booking added." in viewer.post(NEW, form_data(), headers=HX).content.decode()
        assert schedule.viewer_live_bookings(user, NOW) == views.DEMO_LIVE_CAP
        assert viewer.post(NEW, form_data(court="mp-02"), headers=HX).status_code == 429


def test_viewer_days_ahead_is_the_storefront_window():
    assert schedule.VIEWER_DAYS_AHEAD == rules.WINDOW_DAYS - 1


# --- fragment endpoints without htmx -------------------------------------------------------------

BANNER = "Fictional venue · Test mode, no real payments"


@pytest.mark.django_db
class TestWithoutHtmx:
    def test_panel_redirects_to_the_detail_page(self, owner):
        booking = online()

        response = owner.get(booking_url(booking.reference))

        assert response.status_code == 302
        assert response["Location"] == f"/dashboard/bookings/{booking.reference}/"
        assert owner.get(booking_url("KC-ZZZZZZ")).status_code == 404

    def test_panel_with_htmx_is_still_a_bare_partial(self, owner):
        booking = online()

        html = owner.get(booking_url(booking.reference), headers=HX).content.decode()

        assert booking.reference in html and "<html" not in html

    def test_new_form_redirects_to_the_schedule(self, owner):
        day = TODAY.isoformat()

        response = owner.get(f"{NEW}?court=mp-01&hour=15&date={day}")

        assert response.status_code == 302
        assert response["Location"] == f"/dashboard/schedule/?date={day}"

    def test_new_form_with_htmx_is_still_a_bare_partial(self, owner):
        html = owner.get(
            f"{NEW}?court=mp-01&hour=15&date={TODAY.isoformat()}", headers=HX
        ).content.decode()

        assert "<form" in html and "<html" not in html

    def test_valid_create_redirects_to_that_day(self, owner):
        response = owner.post(NEW, form_data())

        assert response.status_code == 303
        assert response["Location"] == f"/dashboard/schedule/?date={TODAY.isoformat()}"
        assert Booking.objects.count() == 1

    def test_invalid_create_is_a_full_page_with_the_error(self, owner):
        response = owner.post(NEW, form_data(kind="block", note=""))
        html = response.content.decode()

        assert response.status_code == 200
        assert BANNER in html and "<html" in html and "hx-disable" in html
        assert "A block needs a note" in html
        assert Booking.objects.count() == 0

    def test_viewer_cancel_refusal_is_a_full_page(self, viewer):
        booking = online()

        response = viewer.post(cancel_url(booking.reference))
        html = response.content.decode()

        assert response.status_code == 403
        assert BANNER in html and "<html" in html
        assert escape(views.CANT_CANCEL) in html

    def test_owner_cancel_redirects_to_the_bookings_day(self, owner):
        booking = online()

        response = owner.post(cancel_url(booking.reference))

        assert response.status_code == 303
        assert response["Location"] == f"/dashboard/schedule/?date={TODAY.isoformat()}"
        booking.refresh_from_db()
        assert booking.status != Status.CONFIRMED

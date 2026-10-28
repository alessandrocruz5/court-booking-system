import re
from collections import Counter
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group, User

from accounts.roles import Role
from bookings import holds, rules
from bookings.holds import Customer
from bookings.models import Booking, Court
from bookings.rules import Source, Status
from dashboard import queries
from dashboard.queries import mask_email, mask_mobile, mask_name, overview, peso

URL = "/dashboard/"
BANNER = "Fictional venue · Test mode, no real payments"
# Monday 2 November 2026, 12:00 in Manila: mid-day, so nothing here straddles midnight.
NOW = datetime(2026, 11, 2, 12, tzinfo=rules.TIME_ZONE)
TODAY = NOW.date()
# Staff can book up to 30 days ahead of the `now` they are given, so history is created "from"
# an earlier date than the pinned `NOW` that the dashboard is read at.
HISTORY_FROM = datetime(2026, 10, 10, 8, tzinfo=rules.TIME_ZONE)


def day_at(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=rules.TIME_ZONE)


def court(code: str) -> Court:
    return Court.objects.get(code=code)


def walk_in(
    code="mp-01",
    day=TODAY,
    hour=14,
    *,
    hours=1,
    sport="badminton",
    coverage="full",
    half=None,
    name="",
    now=HISTORY_FROM,
) -> Booking:
    return holds.create_staff_booking(
        source=Source.WALK_IN,
        court=court(code),
        sport=sport,
        coverage=coverage,
        half=half,
        day=day,
        start_hour=hour,
        hours=hours,
        created_by=None,
        customer_name=name,
        now=now,
    )


def block(code="mp-01", day=TODAY, hour=14, *, hours=1) -> Booking:
    return holds.create_staff_booking(
        source=Source.BLOCK,
        court=court(code),
        sport=None,
        coverage="full",
        half=None,
        day=day,
        start_hour=hour,
        hours=hours,
        created_by=None,
        note="Maintenance",
        now=HISTORY_FROM,
    )


def online(
    code="mp-01",
    day=TODAY,
    hour=14,
    *,
    sport="badminton",
    fee=1000,
    name="Maria Santos",
    email="maria.santos@example.com",
    mobile="+639000000001",
    confirm=True,
    now=None,
) -> Booking:
    """An online booking: a real hold, then (if `confirm`) marked paid directly, as the payment
    webhook would. Created the evening before `day`, or at `now` for a live hold."""
    booking = holds.create_hold(
        court=court(code),
        sport=sport,
        coverage="full",
        day=day,
        start_hour=hour,
        hours=1,
        customer=Customer(name=name, email=email, mobile=mobile),
        now=now or day_at(day - timedelta(days=1), 20),
    )
    if confirm:
        Booking.objects.filter(pk=booking.pk).update(
            status=Status.CONFIRMED,
            payment_method="card",
            paid_at=booking.starts_at - timedelta(hours=1),
            fee_centavos=fee,
            net_centavos=booking.price_centavos - fee,
        )
        booking.refresh_from_db()
    return booking


def make_user(role: Role) -> User:
    user, _ = User.objects.get_or_create(username=f"{role}@example.com")
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


@pytest.fixture
def pinned_clock(monkeypatch):
    monkeypatch.setattr(queries, "timezone", SimpleNamespace(now=lambda: NOW))


def page(client, role: Role):
    client.force_login(make_user(role))
    response = client.get(URL)
    assert response.status_code == 200
    return response.content.decode()


class Tags(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def class_lists(html: str, tag: str, prefix: str) -> list[list[str]]:
    """The class tokens of every `tag` element that has a class starting with `prefix`, in order."""
    found = []
    for name, attrs in Tags(html).tags:
        classes = attrs.get("class", "").split()
        if name == tag and any(c.startswith(prefix) for c in classes):
            found.append(classes)
    return found


def stat_cards(html: str) -> list[tuple[str, str, str]]:
    """(label, value, sub) of every `.stat` card, read from the three paragraphs it holds."""
    cards = []
    for match in re.finditer(r'<div class="stat">(.*?)</div>', html, re.DOTALL):
        label, value, sub = re.findall(r'<p class="stat-[a-z]+">(.*?)</p>', match[1])
        cards.append((label, value, sub))
    return cards


# --- access and shell ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAccess:
    def test_anonymous_is_redirected_to_login(self, client):
        response = client.get(URL)

        assert response.status_code == 302
        assert response["Location"] == "/dashboard/login/"

    def test_root_redirects_to_the_dashboard(self, client):
        response = client.get("/")

        assert response.status_code == 302
        assert response["Location"] == URL

    def test_post_is_not_allowed(self, client):
        client.force_login(make_user(Role.OWNER))

        assert client.post(URL).status_code == 405

    @pytest.mark.parametrize("role", [Role.VIEWER, Role.OWNER])
    def test_staff_get_the_page_with_banner_and_role_badge(self, client, role):
        client.force_login(make_user(role))

        response = client.get(URL)
        html = response.content.decode()

        assert response.status_code == 200
        assert "no-store" in response["Cache-Control"]
        assert BANNER in html
        assert f'<span class="role-badge role-{role}">{role.upper()}</span>' in html
        assert 'action="/dashboard/logout/"' in html

    def test_only_the_viewer_sees_the_masking_note(self, client):
        note = "You're exploring the demo: customers' contact details are masked."

        assert note in page(client, Role.VIEWER)
        client.logout()
        assert "exploring the demo" not in page(client, Role.OWNER)


@pytest.mark.django_db
class TestCsp:
    def test_no_inline_script_and_no_hx_on(self, client, pinned_clock):
        walk_in(name="Juan Dela Cruz", hour=13)
        html = page(client, Role.OWNER)

        tags = Tags(html).tags
        scripts = [attrs for tag, attrs in tags if tag == "script"]
        assert scripts == [{"src": "/static/dashboard/htmx.min.js", "defer": None}]
        assert not [name for _, attrs in tags for name in attrs if name.startswith("hx-on")]
        assert "javascript:" not in html

    def test_htmx_is_configured_without_eval_and_carries_the_csrf_token(self, client):
        html = page(client, Role.VIEWER)

        meta = next(a for t, a in Tags(html).tags if t == "meta" and a.get("name") == "htmx-config")
        assert '"allowEval":false' in meta["content"]
        assert '"allowScriptTags":false' in meta["content"]
        assert '"historyCacheSize":0' in meta["content"]
        assert html.count("hx-headers=") == 2
        assert "X-CSRFToken" in html


# --- queries ------------------------------------------------------------------------------------


@pytest.mark.django_db
class TestToday:
    def test_empty_day(self):
        today = overview(role=Role.OWNER, now=NOW).today

        assert (today.bookings, today.revenue, today.booked_space_hours) == (0, 0, 0)
        assert today.capacity_space_hours == 320
        assert today.utilization_pct == 0

    def test_full_basketball_hour_is_two_of_320_space_hours(self):
        booking = walk_in("bb-1", sport="basketball")

        today = overview(role=Role.OWNER, now=NOW).today

        assert today.bookings == 1
        assert today.revenue == booking.price_centavos
        assert today.booked_space_hours == 2
        assert today.capacity_space_hours == 320
        assert today.utilization_pct == 0.6

    def test_a_half_court_is_one_space_hour(self):
        walk_in("bb-1", sport="basketball", coverage="half", half="A")

        assert overview(role=Role.OWNER, now=NOW).today.booked_space_hours == 1

    def test_only_confirmed_online_and_walk_in_bookings_count(self):
        sold = walk_in("mp-01")
        paid = online("mp-02")
        online("mp-03", confirm=False, now=NOW)  # A live hold: no revenue, no utilization.
        cancelled = walk_in("mp-04")
        holds.release(cancelled, status=Status.CANCELLED, now=NOW)
        block("mp-05")
        walk_in("mp-06", day=TODAY + timedelta(days=1))  # Tomorrow.

        today = overview(role=Role.OWNER, now=NOW).today

        assert today.bookings == 2
        assert today.revenue == sold.price_centavos + paid.price_centavos
        assert today.booked_space_hours == 2

    def test_a_block_reduces_the_capacity(self):
        block("mp-01", hours=2)  # 2 space-hours.
        block("bb-1", hour=10)  # Both halves: 2 more.

        today = overview(role=Role.OWNER, now=NOW).today

        assert today.bookings == 0
        assert today.booked_space_hours == 0
        assert today.capacity_space_hours == 320 - 4

    def test_the_day_is_the_manila_day(self):
        walk_in("mp-01", hour=7)  # 23:00 UTC the day before.
        walk_in("mp-02", hour=22)

        assert overview(role=Role.OWNER, now=NOW).today.bookings == 2


@pytest.mark.django_db
class TestRevenue:
    def test_windows_sums_and_fees(self):
        recent_online = online("mp-01", day=TODAY - timedelta(days=4), fee=1500)  # 7 and 30 days.
        recent_walk_in = walk_in("mp-02", day=TODAY - timedelta(days=1))  # 7 and 30 days.
        older = online("mp-03", day=TODAY - timedelta(days=15), fee=2000)  # 30 days only.
        too_old = online("mp-04", day=TODAY - timedelta(days=25), fee=900, sport="pickleball")
        # Ignored: cancelled, a block, and not yet started.
        holds.release(walk_in("mp-05", day=TODAY - timedelta(days=2)), status=Status.CANCELLED)
        block("mp-06", day=TODAY - timedelta(days=2))
        walk_in("mp-07", hour=14)

        result = overview(role=Role.OWNER, now=NOW)

        gross_7d = recent_online.price_centavos + recent_walk_in.price_centavos
        assert result.revenue_7d.gross == gross_7d
        assert result.revenue_7d.fees == 1500  # The walk-in is cash: fee 0.
        assert result.revenue_7d.net == gross_7d - 1500

        gross_30d = gross_7d + older.price_centavos + too_old.price_centavos
        assert result.revenue_30d.gross == gross_30d
        assert result.revenue_30d.fees == 1500 + 2000 + 900
        assert result.revenue_30d.net == gross_30d - 4400

    def test_by_sport_orders_by_gross_with_bar_widths(self):
        a = online("mp-01", day=TODAY - timedelta(days=2), sport="pickleball")
        b = walk_in("mp-02", day=TODAY - timedelta(days=3), sport="pickleball")
        c = walk_in("tn-1", day=TODAY - timedelta(days=3), sport="tennis")

        rows = overview(role=Role.OWNER, now=NOW).by_sport_30d

        assert [(r.sport, r.bookings) for r in rows] == [("pickleball", 2), ("tennis", 1)]
        assert rows[0].gross == a.price_centavos + b.price_centavos
        assert rows[0].label == "Pickleball"
        assert rows[0].width == 100
        assert rows[1].gross == c.price_centavos
        assert rows[1].width == 55  # 50,000 of 90,000 is 55.6%: the nearest 5 is 55.

    def test_bar_widths_are_relative_to_the_top_sport_in_steps_of_five(self):
        friday, saturday = TODAY - timedelta(days=3), TODAY - timedelta(days=2)
        walk_in("mp-01", day=saturday, sport="pickleball")  # 50,000 at the weekend rate...
        walk_in("mp-02", day=friday, sport="pickleball")  # ...and 40,000: 90,000, the top sport.
        walk_in("tn-1", day=saturday, sport="tennis")  # 70,000: 77.8% rounds to 80.
        walk_in("mp-03", day=friday, sport="badminton")  # 35,000: 38.9% rounds to 40.

        rows = overview(role=Role.OWNER, now=NOW).by_sport_30d

        assert [(r.sport, r.gross, r.width) for r in rows] == [
            ("pickleball", 90_000, 100),
            ("tennis", 70_000, 80),
            ("badminton", 35_000, 40),
        ]

    def test_empty(self):
        result = overview(role=Role.OWNER, now=NOW)

        assert result.revenue_7d.gross == 0
        assert result.by_sport_30d == ()


def fill_mondays(*hours_per_monday: int) -> None:
    """Book `mp-01` at 10:00 for the given number of hours on each of the window's four Mondays."""
    mondays = [date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 19), date(2026, 10, 26)]
    created = datetime(2026, 10, 1, tzinfo=rules.TIME_ZONE)
    for monday, hours in zip(mondays, hours_per_monday, strict=True):
        walk_in("mp-01", day=monday, hour=10, hours=hours, now=created)


@pytest.mark.django_db
class TestHeatmap:
    def test_shape_and_an_empty_venue(self):
        heatmap = overview(role=Role.OWNER, now=NOW).heatmap

        assert heatmap.hours[0] == "07" and heatmap.hours[-1] == "22" and len(heatmap.hours) == 16
        assert [row.label for row in heatmap.rows] == list(queries.WEEKDAYS)
        assert all(len(row.cells) == 16 for row in heatmap.rows)
        assert all(cell.pct == 0 and cell.level == 0 for row in heatmap.rows for cell in row.cells)

    def test_utilization_by_weekday_and_hour(self):
        monday = date(2026, 10, 26)
        # All 20 spaces on one of the 4 Mondays at 10:00: 20 of 80 space-hours.
        for n in range(1, 13):
            walk_in(f"mp-{n:02d}", day=monday, hour=10)
        for n in range(1, 5):
            walk_in(f"tn-{n}", day=monday, hour=10, sport="tennis")
        for n in range(1, 3):
            walk_in(f"bb-{n}", day=monday, hour=10, sport="basketball")
        # Today is not in the window, and neither is a booking before it.
        walk_in("mp-01", day=TODAY, hour=10)
        walk_in(
            "mp-02",
            day=date(2026, 10, 4),
            hour=10,
            now=datetime(2026, 10, 1, tzinfo=rules.TIME_ZONE),
        )

        rows = overview(role=Role.OWNER, now=NOW).heatmap.rows

        assert (rows[0].cells[3].pct, rows[0].cells[3].level) == (25, 2)
        assert sum(cell.pct for row in rows for cell in row.cells) == 25

    def test_levels_run_from_0_to_9_one_per_ten_percent(self, monkeypatch):
        monkeypatch.setattr(queries, "SPACE_COUNT", 1)  # One space: a cell holds 4 space-hours.
        fill_mondays(3, 2, 2, 1)  # Mon 10:00 is booked 4 times, 11:00 3 times, 12:00 once.

        cells = overview(role=Role.OWNER, now=NOW).heatmap.rows[0].cells

        rest = overview(role=Role.OWNER, now=NOW).heatmap.rows[1:]
        assert [(cell.pct, cell.level) for cell in cells[3:6]] == [(100, 9), (75, 7), (25, 2)]
        assert cells[0].level == 0
        assert {cell.level for row in rest for cell in row.cells} == {0}

    def test_hours_and_weekdays_follow_manila_time(self):
        walk_in("mp-01", day=date(2026, 10, 27), hour=7)  # Tuesday 07:00 is Monday 23:00 UTC.
        walk_in("mp-01", day=date(2026, 11, 1), hour=22)  # Sunday 22:00, the last cell.

        rows = overview(role=Role.OWNER, now=NOW).heatmap.rows

        assert rows[1].cells[0].pct == 1  # 1 of 80 space-hours rounds to 1.
        assert rows[6].cells[15].pct == 1
        assert rows[0].cells[0].pct == 0

    def test_blocks_shrink_the_denominator_and_pending_holds_do_not_count(self):
        monday = date(2026, 10, 26)
        for n in range(1, 9):
            block(f"mp-{n:02d}", day=monday, hour=10)
        walk_in("tn-1", day=monday, hour=10, sport="tennis")
        online("tn-2", day=monday, hour=10, sport="tennis", confirm=False)  # Lapsed by now.

        cell = overview(role=Role.OWNER, now=NOW).heatmap.rows[0].cells[3]

        assert cell.pct == round(100 * 1 / (80 - 8))

    def test_cancelled_bookings_do_not_count(self):
        booking = walk_in("mp-01", day=date(2026, 10, 26), hour=10)
        holds.release(booking, status=Status.CANCELLED, now=NOW)

        assert overview(role=Role.OWNER, now=NOW).heatmap.rows[0].cells[3].pct == 0


@pytest.mark.django_db
class TestUpcoming:
    def test_next_three_hours_only_in_start_order(self):
        walk_in("mp-02", hour=13, name="Later Booker")
        walk_in("mp-01", hour=12, name="Juan Dela Cruz")  # Starts exactly now: included.
        walk_in("mp-03", hour=15, name="Too Late")  # NOW + 3h: excluded.
        walk_in("mp-04", hour=11, name="Already Started")
        block("mp-05", hour=13)

        rows = overview(role=Role.OWNER, now=NOW).upcoming

        assert [(r.name, r.court, r.when, r.source) for r in rows] == [
            ("Juan Dela Cruz", "Court 1", "12:00 PM - 1:00 PM", "Walk-in"),
            ("Later Booker", "Court 2", "1:00 PM - 2:00 PM", "Walk-in"),
        ]

    def test_half_court_and_sport_are_described(self):
        walk_in("bb-1", hour=13, sport="basketball", coverage="half", half="B")

        (row,) = overview(role=Role.OWNER, now=NOW).upcoming

        assert (row.court, row.coverage, row.sport) == (
            "Basketball Court 1",
            "Half B",
            "Basketball",
        )

    def test_the_viewer_gets_masked_names_and_the_owner_raw_ones(self):
        walk_in("mp-01", hour=13, name="Juan Dela Cruz")

        (viewer,) = overview(role=Role.VIEWER, now=NOW).upcoming
        (owner,) = overview(role=Role.OWNER, now=NOW).upcoming

        assert viewer.name == "Juan D."
        assert owner.name == "Juan Dela Cruz"


@pytest.mark.django_db
class TestAlerts:
    def test_counts_needs_refund_and_only_unexpired_holds(self):
        live = online("mp-01", confirm=False, now=NOW)
        online("mp-02", confirm=False, now=NOW - timedelta(minutes=30))  # Lapsed hold.
        paid_late = online("mp-03", confirm=False, now=NOW)
        holds.release(paid_late, status=Status.NEEDS_REFUND, now=NOW)

        alerts = overview(role=Role.OWNER, now=NOW).alerts

        assert live.status == Status.PENDING
        assert (alerts.needs_refund, alerts.active_holds) == (1, 1)


# --- the page -----------------------------------------------------------------------------------


@pytest.mark.django_db
class TestPage:
    def test_kpis_and_revenue_render(self, client, pinned_clock):
        booking = walk_in("mp-01", hour=14)
        walk_in("mp-02", day=TODAY - timedelta(days=1))
        html = page(client, Role.OWNER)

        assert peso(booking.price_centavos) in html
        assert "Utilization" in html and "1 of 320 space-hours" in html
        assert "Last 7 days" in html and "Last 30 days" in html
        assert '<table class="heatmap">' in html and 'scope="row">Mon</th>' in html
        assert class_lists(html, "span", "ov-fill") == [["ov-fill", "ov-fill-badminton", "w-100"]]

    def test_the_stat_cards(self, client, pinned_clock):
        walk_in("mp-01", hour=14)  # Today, after `NOW`: counted today, but not yet in the 7 days.
        online("mp-02", day=TODAY - timedelta(days=2), fee=1500)  # 45,000 at the weekend rate.
        online("mp-03", confirm=False, now=NOW)  # A live hold.
        html = page(client, Role.OWNER)

        assert ("Revenue · 7 days", "₱450", "Net ₱435 after fees") in stat_cards(html)
        assert ("Bookings · today", "1", "₱350 revenue") in stat_cards(html)
        assert ("Utilization · today", "0.3%", "1 of 320 space-hours") in stat_cards(html)
        assert (
            "Active holds",
            "1",
            f"Unpaid, held for {rules.HOLD_MINUTES} minutes",
        ) in stat_cards(html)
        assert len(stat_cards(html)) == 4

    def test_the_bars_take_their_width_from_the_top_sport(self, client, pinned_clock):
        friday, saturday = TODAY - timedelta(days=3), TODAY - timedelta(days=2)
        walk_in("mp-01", day=saturday, sport="pickleball")  # 90,000 with the next one: the top.
        walk_in("mp-02", day=friday, sport="pickleball")
        walk_in("tn-1", day=saturday, sport="tennis")  # 70,000: 77.8%.
        walk_in("mp-03", day=friday, sport="badminton")  # 35,000: 38.9%.
        html = page(client, Role.OWNER)

        assert class_lists(html, "span", "ov-fill") == [
            ["ov-fill", "ov-fill-pickleball", "w-100"],
            ["ov-fill", "ov-fill-tennis", "w-80"],
            ["ov-fill", "ov-fill-badminton", "w-40"],
        ]
        assert "₱900" in html and "2 bookings" in html and "1 booking<" in html

    def test_the_heatmap_cells_take_their_shade_from_the_level(
        self, client, pinned_clock, monkeypatch
    ):
        monkeypatch.setattr(queries, "SPACE_COUNT", 1)  # One space: a cell holds 4 space-hours.
        fill_mondays(3, 2, 2, 1)
        html = page(client, Role.OWNER)

        levels = Counter(classes[0] for classes in class_lists(html, "td", "heat-"))
        assert levels == {"heat-0": 109, "heat-2": 1, "heat-7": 1, "heat-9": 1}  # 7 x 16 cells.
        assert '<td class="heat-9" title="100%">100</td>' in html
        assert '<td class="heat-0" title="0%">0</td>' in html

    def test_one_h1_and_no_inline_styles(self, client, pinned_clock):
        walk_in("mp-01", hour=13, name="Juan Dela Cruz")
        html = page(client, Role.OWNER)
        tags = Tags(html).tags

        assert [attrs for tag, attrs in tags if tag == "h1"] == [{"class": "dash-heading"}]
        assert '<h1 class="dash-heading">Overview</h1>' in html
        assert "<title>Overview · Kalaro Courts staff</title>" in html
        assert not [tag for tag, attrs in tags if tag == "style" or "style" in attrs]

    def test_refund_alert_only_when_there_are_any(self, client, pinned_clock):
        assert "need a refund" not in page(client, Role.OWNER)

        paid_late = online("mp-01", confirm=False, now=NOW)
        holds.release(paid_late, status=Status.NEEDS_REFUND, now=NOW)
        html = page(client, Role.OWNER)

        assert 'role="status"' in html
        assert "1 paid booking needs a refund in the PayMongo dashboard (test mode)." in html

        holds.release(online("mp-02", confirm=False, now=NOW), status=Status.NEEDS_REFUND, now=NOW)
        assert "2 paid bookings need a refund" in page(client, Role.OWNER)

    def test_the_viewer_never_receives_contact_details_or_full_names(self, client, pinned_clock):
        online(
            "mp-01",
            hour=13,
            name="Maria Santos",
            email="maria.santos@example.com",
            mobile="+639000000001",
        )
        walk_in("mp-02", hour=14, name="Juan Dela Cruz")

        html = page(client, Role.VIEWER)

        assert "Maria S." in html and "Juan D." in html
        for secret in ("maria.santos", "@example.com", "639000000001", "Santos", "Dela Cruz"):
            assert secret not in html
        client.logout()
        assert "Juan Dela Cruz" in page(client, Role.OWNER)

    def test_active_holds_note_uses_the_hold_minutes_rule(self, client, pinned_clock, monkeypatch):
        assert overview(role=Role.OWNER, now=NOW).alerts.hold_minutes == rules.HOLD_MINUTES
        assert f"Unpaid, held for {rules.HOLD_MINUTES} minutes" in page(client, Role.OWNER)

        monkeypatch.setattr(queries, "HOLD_MINUTES", 37)
        assert "Unpaid, held for 37 minutes" in page(client, Role.OWNER)

    def test_empty_states(self, client, pinned_clock):
        html = page(client, Role.OWNER)

        assert "Nothing starts in the next 3 hours." in html
        assert "No bookings in the last 30 days." in html


# --- helpers ------------------------------------------------------------------------------------


class TestMasks:
    @pytest.mark.parametrize(
        ("email", "masked"),
        [
            ("juan.cruz@example.com", "j•••@example.com"),
            ("a@b.ph", "a•••@b.ph"),
            ("no-at-sign", "•••"),
            ("@example.com", "•••"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_mask_email(self, email, masked):
        assert mask_email(email) == masked

    @pytest.mark.parametrize(
        ("mobile", "masked"),
        [("+639171234567", "•••67"), ("09171234567", "•••67"), ("7", "•••"), ("", ""), (None, "")],
    )
    def test_mask_mobile(self, mobile, masked):
        assert mask_mobile(mobile) == masked

    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("Juan Dela Cruz", "Juan D."),
            ("Maria Santos", "Maria S."),
            ("  Juan   Cruz ", "Juan C."),
            ("Madonna", "M•••"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_mask_name(self, name, masked):
        assert mask_name(name) == masked

    def test_name_for_masks_everyone_but_the_owner(self):
        assert queries.name_for(Role.OWNER, "Juan Dela Cruz") == "Juan Dela Cruz"
        assert queries.name_for(Role.VIEWER, "Juan Dela Cruz") == "Juan D."
        assert queries.name_for(None, "Juan Dela Cruz") == "Juan D."

    @pytest.mark.parametrize(
        ("centavos", "text"),
        [(0, "₱0"), (123456, "₱1,235"), (49, "₱0"), (50, "₱1"), (-250000, "-₱2,500")],
    )
    def test_peso(self, centavos, text):
        assert peso(centavos) == text


def test_space_count_matches_the_venue():
    assert queries.SPACE_COUNT == 20
    assert queries.HOURS_PER_DAY == 16

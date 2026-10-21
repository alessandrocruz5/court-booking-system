import logging
from datetime import UTC, datetime, timedelta
from html import escape
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client

from accounts.roles import Role
from bookings import holds, pricing, rules
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


def court(code: str) -> Court:
    return Court.objects.get(code=code)


def make_user(role: Role) -> User:
    user, _ = User.objects.get_or_create(username=f"{role}@example.com")
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


def walk_in(
    code="mp-01", day=TODAY, hour=14, *, sport="badminton", name="", is_demo=False, now=NOW
):
    return holds.create_staff_booking(
        source=Source.WALK_IN,
        court=court(code),
        sport=sport,
        coverage="full",
        half=None,
        day=day,
        start_hour=hour,
        hours=1,
        created_by=None,
        customer_name=name,
        is_demo=is_demo,
        now=now,
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
    """Start tags with their attributes, plus each `<tbody>` row's cells (tag, attrs)."""

    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.rows = []
        self.in_body = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if tag == "tbody":
            self.in_body = True
        elif self.in_body and tag == "tr":
            self.rows.append([])
        elif self.in_body and tag in ("th", "td"):
            self.rows[-1].append((tag, attrs))

    def handle_endtag(self, tag):
        if tag == "tbody":
            self.in_body = False


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

    def test_schedule_is_in_the_nav(self, owner):
        html = owner.get(URL).content.decode()

        assert '<a href="/dashboard/schedule/" aria-current="page">Schedule</a>' in html
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
        assert grid.hours[0] == "7 AM" and grid.hours[-1] == "10 PM" and len(grid.hours) == 16
        assert [row.label for row in grid.rows[:3]] == [
            "Basketball Court 1 · Half A",
            "Basketball Court 1 · Half B",
            "Basketball Court 2 · Half A",
        ]
        assert grid.rows[4].label == "Tennis Court 1"
        assert grid.rows[-1].label == "Court 12"

    def test_page_table_has_20_rows_of_16_hour_columns(self, owner):
        html = owner.get(URL).content.decode()

        rows = Html(html).rows
        assert len(rows) == 20
        for row in rows:
            assert row[0][0] == "th"
            assert sum(int(attrs.get("colspan", 1)) for _, attrs in row[1:]) == 16

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
            assert segment.css == "slot-walkin"
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

        assert cells[paid.reference].css == "slot-online"
        assert not cells[paid.reference].can_cancel  # A real visitor's online booking.
        assert cells[demo.reference].is_demo and cells[demo.reference].can_cancel
        assert cells[hold.reference].css == "slot-online slot-pending"
        assert cells[hold.reference].status == Status.PENDING
        assert cells[blocked.reference].css == "slot-block"
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
        assert cells[0].css == "slot-past" and cells[5].css == "slot-free"
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
        assert 'class="schedule"' in html
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
        for css in ("slot-online", "slot-walkin", "slot-block", "slot-pending", "slot-past"):
            assert css in html
        assert "Dela Cruz" not in html and "Juan D." in html

    def test_hx_config_swaps_refusals(self, owner):
        html = owner.get(URL).content.decode()

        assert '{"code":"403|429","swap":true,"error":false}' in html


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
        assert "<html" not in html and 'class="schedule"' in html
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
        assert 'class="schedule"' in html and booking.reference in html
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

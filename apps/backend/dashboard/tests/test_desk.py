"""The Front desk pages: the lookup, the suggestions and the check-in action."""

from datetime import timedelta

import pytest

from accounts.roles import Role
from bookings.models import Booking
from bookings.rules import Source, Status
from core import ratelimit
from dashboard import views
from dashboard.queries import mask_email, mask_mobile
from dashboard.tests.test_bookings import (  # noqa: F401 (`pinned_clock`: an autouse fixture)
    EMAIL,
    MOBILE,
    NAME,
    NOW,
    TODAY,
    assert_csp_safe,
    make,
    make_user,
    pinned_clock,
)

URL = "/dashboard/desk/"
SUGGEST = "/dashboard/desk/suggest/"
HX = {"HX-Request": "true"}
DEMO_NAME = "Maria Santos"


@pytest.fixture
def owner(client):
    client.force_login(make_user(Role.OWNER))
    return client


@pytest.fixture
def viewer(client):
    client.force_login(make_user(Role.VIEWER))
    return client


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
    assert not ratelimit.hit(
        "staff_write",
        "127.0.0.1",
        limit=views.WRITE_LIMIT,
        window_seconds=views.WRITE_WINDOW_SECONDS,
    )


def html_of(response) -> str:
    html = response.content.decode()
    assert_csp_safe(html)
    return html


# --- access -------------------------------------------------------------------------------------


@pytest.mark.django_db
class TestAccess:
    @pytest.mark.parametrize("url", [URL, f"{URL}?q=KC-T00001", f"{SUGGEST}?q=Juan"])
    def test_anonymous_is_redirected_to_login(self, client, url):
        make()

        response = client.get(url)

        assert response.status_code == 302
        assert response["Location"] == "/dashboard/login/"

    def test_anonymous_check_in_is_redirected_and_changes_nothing(self, client):
        booking = make()

        assert client.post(check_in_url(booking.reference)).status_code == 302
        assert client.post(check_in_url(booking.reference), headers=HX)["HX-Redirect"] == (
            "/dashboard/login/"
        )
        booking.refresh_from_db()
        assert booking.checked_in_at is None

    def test_check_in_is_post_only_and_suggest_get_only(self, owner):
        booking = make()

        assert owner.get(check_in_url(booking.reference)).status_code == 405
        assert owner.post(SUGGEST, {"q": "Juan"}).status_code == 405
        assert owner.post(URL).status_code == 405

    def test_a_nul_or_unknown_reference_is_a_404(self, owner):
        assert owner.post(check_in_url("KC-%00AAAA"), headers=HX).status_code == 404
        assert owner.post(check_in_url("KC-NOPE00"), headers=HX).status_code == 404

    def test_desk_is_first_in_the_nav_with_the_arriving_badge(self, owner):
        make("KC-T00001", hour=13)
        make("KC-T00002", hour=14)
        make("KC-T00003", hour=19)  # Outside the next 3 hours.

        html = html_of(owner.get(URL))

        assert (
            '<a href="/dashboard/desk/" aria-current="page">Front desk<span id="desk-badge" '
            'class="nav-badge">2<span class="visually-hidden"> arriving next</span></span></a>'
        ) in html
        assert html.count('aria-current="page"') == 1
        assert html.index(">Front desk<") < html.index(">Schedule</a>")
        assert "<title>Front desk · Kalaro Courts staff</title>" in html
        assert html.count("<h1") == 1 and '<h1 class="dash-heading">Front desk</h1>' in html
        assert "Fictional venue" in html

    def test_the_badge_is_empty_with_nobody_arriving(self, owner):
        html = html_of(owner.get(URL))

        assert '<span id="desk-badge" class="nav-badge"></span>' in html
        assert "Nobody else is due in the next 3 hours." in html

    def test_other_pages_link_to_the_desk_without_a_badge(self, owner):
        make()

        html = html_of(owner.get("/dashboard/schedule/"))

        assert '<a href="/dashboard/desk/">Front desk</a>' in html


# --- the page -----------------------------------------------------------------------------------


@pytest.mark.django_db
class TestPage:
    def test_lookup_form_is_a_plain_get_with_a_mono_autofocus_input(self, owner):
        html = html_of(owner.get(URL))

        assert '<form class="desk-lookup-form" method="get" action="/dashboard/desk/"' in html
        assert (
            '<input id="desk-q" class="desk-input" type="text" name="q" value="" '
            'placeholder="KC-XXXXXX"'
        ) in html
        assert " autofocus " in html
        assert 'hx-get="/dashboard/desk/suggest/"' in html
        assert 'hx-trigger="input changed delay:250ms"' in html
        assert 'hx-target="#suggest"' in html
        assert '<div id="desk" class="desk">' in html and '<div id="suggest"' in html
        assert "no-store" in owner.get(URL)["Cache-Control"]

    def test_owner_lookup_shows_the_full_contact(self, owner):
        make("KC-T00001")

        html = html_of(owner.get(URL, {"q": " t00001 "}))

        assert 'value="t00001"' in html
        assert "KC-T00001" in html
        assert NAME in html and EMAIL in html and MOBILE in html
        assert "desk-result desk-result-ready" in html
        assert 'hx-post="/dashboard/desk/check-in/KC-T00001/"' in html
        assert 'href="/dashboard/schedule/?date=2026-11-02"' in html
        assert "₱300" in html

    def test_viewer_lookup_is_masked(self, viewer):
        make("KC-T00001")

        html = html_of(viewer.get(URL, {"q": "KC-T00001"}))

        assert "Juan D." in html
        assert mask_email(EMAIL) in html and mask_mobile(MOBILE) in html
        assert NAME not in html and EMAIL not in html and MOBILE not in html
        # A real visitor's online booking: the viewer can't check it in.
        assert 'hx-post="/dashboard/desk/check-in/KC-T00001/"' not in html
        assert "desk-result-ready" not in html

    def test_not_found(self, owner):
        html = html_of(owner.get(URL, {"q": "w3pe7v"}))

        assert "<strong>No booking found for KC-W3PE7V.</strong>" in html
        assert "desk-result" not in html

    def test_without_js_a_name_lookup_lists_its_matches(self, owner):
        make("KC-T00001", hour=14)

        html = html_of(owner.get(URL, {"q": "Juan"}))

        assert "No booking found for JUAN." in html
        assert 'class="desk-suggest-row" href="/dashboard/desk/?q=KC-T00001"' in html

    def test_wrong_day_and_ended_show_their_warning(self, owner):
        make("KC-T00001", day=TODAY + timedelta(days=4))
        make("KC-T00002", hour=9)

        tomorrow = html_of(owner.get(URL, {"q": "KC-T00001"}))
        ended = html_of(owner.get(URL, {"q": "KC-T00002"}))

        assert "This booking is for Friday 6 Nov — not today." in tomorrow
        assert "Fri 6, 2 PM – 3 PM" in tomorrow
        assert "This session has already ended." in ended
        assert "check-in/KC-T00002/" not in ended

    def test_stats_arriving_and_on_court(self, owner):
        make("KC-T00001", hour=13, source=Source.WALK_IN, price_centavos=20000)
        on_court = make(
            "KC-T00002", hour=11, hours=2, ends_at=NOW + timedelta(hours=1), customer_name=DEMO_NAME
        )
        Booking.objects.filter(pk=on_court.pk).update(checked_in_at=NOW - timedelta(hours=1))

        html = html_of(owner.get(URL))

        assert ">2</p>" in html and "1 walk-in<" in html
        assert "₱500" in html
        assert '1 PM<span class="desk-row-tag desk-row-tag-next">NEXT</span>' in html
        assert 'action="/dashboard/desk/check-in/KC-T00001/"' in html
        assert '<span class="tag tag-badminton"></span>' in html
        assert "1 checked in" in html
        assert 'href="/dashboard/bookings/KC-T00002/"' in html and "until 1 PM" in html

    def test_viewer_gets_two_demo_references_to_try(self, viewer):
        make("KC-T00001", hour=13)  # Real: never a hint.
        make("KC-D00001", hour=13, is_demo=True)
        make("KC-D00002", hour=14, is_demo=True)
        make("KC-D00003", hour=14, is_demo=True)

        html = html_of(viewer.get(URL))

        assert (
            '<p class="desk-hint">Try <a class="desk-ref" href="/dashboard/desk/?q=KC-D00001">'
            in (html)
        )
        assert ">KC-D00001</a> or <a" in html and ">KC-D00002</a></p>" in html
        assert '?q=KC-D00003">KC-D00003</a></p>' not in html

    def test_hint_is_omitted_for_the_owner_and_without_demo_bookings(self, owner, client):
        make("KC-D00001", hour=13, is_demo=True)

        assert "desk-hint" not in html_of(owner.get(URL))
        Booking.objects.all().delete()
        client.force_login(make_user(Role.VIEWER))
        assert "desk-hint" not in html_of(client.get(URL))


# --- suggestions --------------------------------------------------------------------------------


@pytest.mark.django_db
class TestSuggest:
    def test_owner_suggestions_by_name_and_reference(self, owner):
        make("KC-T00001", hour=14)

        by_name = html_of(owner.get(SUGGEST, {"q": "juan"}, headers=HX))
        by_reference = html_of(owner.get(SUGGEST, {"q": "t0000"}, headers=HX))

        for html in (by_name, by_reference):
            assert "<html" not in html and 'id="desk"' not in html
            assert ">KC-T00001</span>" in html and NAME in html
            assert "Today, 2 PM – 3 PM" in html

    def test_viewer_matches_a_demo_name_but_never_a_real_one(self, viewer):
        make("KC-T00001", hour=14)  # Real: Juan Dela Cruz.
        make("KC-D00001", hour=15, customer_name=DEMO_NAME, is_demo=True)

        demo = html_of(viewer.get(SUGGEST, {"q": "maria"}, headers=HX))
        real = html_of(viewer.get(SUGGEST, {"q": "juan"}, headers=HX))

        assert "KC-D00001" in demo and "Maria S." in demo and DEMO_NAME not in demo
        assert "KC-T00001" not in real and "Juan" not in real
        assert "desk-suggest-list" not in real

    def test_under_two_characters_is_an_empty_partial(self, owner):
        make("KC-T00001", hour=14)

        response = owner.get(SUGGEST, {"q": "j"}, headers=HX)

        assert response.status_code == 200
        assert response.content.decode().strip() == ""

    def test_non_htmx_is_never_a_bare_fragment(self, owner):
        make("KC-T00001", hour=14)

        response = owner.get(SUGGEST, {"q": "Juan"})
        empty = owner.get(SUGGEST)

        assert response.status_code == 302
        assert response["Location"] == "/dashboard/desk/?q=Juan"
        assert empty["Location"] == "/dashboard/desk/"
        assert "desk-suggest" not in response.content.decode()


# --- checking in --------------------------------------------------------------------------------


@pytest.mark.django_db
class TestCheckIn:
    def test_happy_path(self, owner):
        booking = make("KC-T00001", hour=14)

        response = owner.post(check_in_url(booking.reference), headers=HX)
        html = html_of(response)

        assert response.status_code == 200
        assert "<html" not in html and html.lstrip().startswith('<div id="desk" class="desk">')
        assert (
            '<div id="toast" class="toast" role="status" aria-live="polite" hx-swap-oob="true">'
            '<span aria-hidden="true">✓ </span>Juan Dela Cruz checked in · Court 1</div>'
        ) in html
        assert '<span id="desk-badge" class="nav-badge" hx-swap-oob="true">' in html
        assert "Checked in at 12:00 PM" in html  # The result card, looked up by its reference.
        assert 'value="KC-T00001"' in html
        assert "no-store" in response["Cache-Control"]
        booking.refresh_from_db()
        assert booking.checked_in_at == NOW
        assert booking.checked_in_by == make_user(Role.OWNER)

    def test_without_htmx_it_redirects_to_the_lookup(self, owner):
        booking = make("KC-T00001", hour=14)

        response = owner.post(check_in_url(booking.reference))

        assert response.status_code == 303
        assert response["Location"] == "/dashboard/desk/?q=KC-T00001"
        booking.refresh_from_db()
        assert booking.checked_in_at == NOW

    def test_double_check_in_is_a_no_op_success(self, owner):
        booking = make("KC-T00001", hour=14)
        earlier = NOW - timedelta(minutes=5)
        Booking.objects.filter(pk=booking.pk).update(checked_in_at=earlier)

        response = owner.post(check_in_url(booking.reference), headers=HX)

        assert response.status_code == 200
        assert "Juan Dela Cruz checked in · Court 1" in html_of(response)
        booking.refresh_from_db()
        assert booking.checked_in_at == earlier and booking.checked_in_by is None

    def test_viewer_double_check_in_spends_no_budget(self, viewer):
        booking = make("KC-D00001", hour=14, is_demo=True)
        assert viewer.post(check_in_url(booking.reference), headers=HX).status_code == 200
        spend_viewer_budget()

        response = viewer.post(check_in_url(booking.reference), headers=HX)

        assert response.status_code == 200
        assert "Juan D. checked in · Court 1" in html_of(response)

    def test_a_cancelled_booking_checked_in_earlier_is_refused(self, owner):
        booking = make("KC-T00001", hour=14, status=Status.CANCELLED)
        Booking.objects.filter(pk=booking.pk).update(checked_in_at=NOW - timedelta(minutes=5))

        response = owner.post(check_in_url(booking.reference), headers=HX)

        assert response.status_code == 403
        assert "checked in ·" not in html_of(response)

    def test_viewer_cannot_check_in_a_real_online_booking(self, viewer):
        booking = make("KC-T00001", hour=14)

        response = viewer.post(check_in_url(booking.reference), headers=HX)
        html = html_of(response)

        assert response.status_code == 403
        assert "You can&#x27;t check in this booking." in html
        assert response["HX-Retarget"] == "#desk"
        assert response["HX-Reswap"] == "outerHTML"
        assert html.lstrip().startswith('<div id="desk" class="desk">')
        assert 'id="toast"' not in html
        assert NAME not in html and EMAIL not in html
        booking.refresh_from_db()
        assert booking.checked_in_at is None

    def test_viewer_can_check_in_a_demo_booking(self, viewer):
        booking = make("KC-D00001", hour=14, is_demo=True)

        response = viewer.post(check_in_url(booking.reference), headers=HX)
        html = html_of(response)

        assert response.status_code == 200
        assert "Juan D. checked in · Court 1" in html
        assert NAME not in html
        booking.refresh_from_db()
        assert booking.checked_in_at == NOW
        assert booking.checked_in_by == make_user(Role.VIEWER)

    def test_viewer_budget_429(self, viewer):
        booking = make("KC-D00001", hour=14, is_demo=True)
        spend_viewer_budget()

        response = viewer.post(check_in_url(booking.reference), headers=HX)

        assert response.status_code == 429
        assert views.DEMO_LIMIT in html_of(response)
        assert response["HX-Retarget"] == "#desk"
        booking.refresh_from_db()
        assert booking.checked_in_at is None

    def test_the_owner_is_not_limited(self, owner):
        booking = make("KC-T00001", hour=14)
        spend_viewer_budget()

        assert owner.post(check_in_url(booking.reference), headers=HX).status_code == 200

    @pytest.mark.parametrize(
        ("fields", "warning"),
        [
            ({"day": TODAY + timedelta(days=1)}, "This booking is for Tuesday 3 Nov — not today."),
            ({"hour": 9}, "This session has already ended."),
        ],
    )
    def test_wrong_day_and_ended_are_refused_with_a_message(self, owner, fields, warning):
        booking = make("KC-T00001", **fields)

        response = owner.post(check_in_url(booking.reference), headers=HX)
        html = html_of(response)

        assert response.status_code == 403
        assert "You can&#x27;t check in this booking." in html
        assert warning.replace("'", "&#x27;") in html
        booking.refresh_from_db()
        assert booking.checked_in_at is None

    @pytest.mark.parametrize(
        ("fields", "message"),
        [
            ({"day": TODAY + timedelta(days=1)}, views.CHECK_IN_ERRORS["not_today"]),
            ({"hour": 9}, views.CHECK_IN_ERRORS["ended"]),
            ({"status": Status.CANCELLED}, views.CHECK_IN_ERRORS["not_confirmed"]),
        ],
    )
    def test_a_check_in_error_maps_to_a_friendly_message(self, owner, monkeypatch, fields, message):
        """The booking changed after the permission check (a race): `bookings.checkin` refuses."""
        monkeypatch.setattr(views, "can_check_in", lambda *args, **kwargs: True)
        booking = make("KC-T00001", **fields)

        response = owner.post(check_in_url(booking.reference), headers=HX)

        assert response.status_code == 403
        assert message.replace("'", "&#x27;") in html_of(response)
        booking.refresh_from_db()
        assert booking.checked_in_at is None

    def test_a_refusal_without_htmx_is_never_a_bare_fragment(self, viewer):
        booking = make("KC-T00001", hour=14)

        response = viewer.post(check_in_url(booking.reference))
        html = html_of(response)

        assert response.status_code == 403
        assert "<html" in html and "Fictional venue" in html
        assert "You can&#x27;t check in this booking." in html
        assert "<div hx-disable>" in html

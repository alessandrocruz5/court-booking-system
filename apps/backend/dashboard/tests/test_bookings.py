import re
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group, User
from django.http import QueryDict

from accounts.roles import Role
from bookings import holds, rules
from bookings.holds import Customer
from bookings.models import Booking, Court
from bookings.rules import Source, Status
from core import ratelimit
from dashboard import queries, views

URL = "/dashboard/bookings/"
HX = {"HX-Request": "true"}
# Monday 2 November 2026, 12:00 in Manila.
NOW = datetime(2026, 11, 2, 12, tzinfo=rules.TIME_ZONE)
TODAY = NOW.date()
RATE_NOW = datetime(2026, 11, 2, 4, 1, tzinfo=UTC)

EMAIL = "juan.cruz@example.com"
MOBILE = "+639171234567"
NAME = "Juan Dela Cruz"


def detail_url(reference: str) -> str:
    return f"{URL}{reference}/"


def cancel_url(reference: str) -> str:
    return f"/dashboard/schedule/booking/{reference}/cancel/"


def make_user(role: Role) -> User:
    user, _ = User.objects.get_or_create(username=f"{role}@example.com")
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


def make(reference="KC-T00001", *, hour=14, day=TODAY, **fields) -> Booking:
    """A booking row written directly (no slot lock): enough for what the list reads."""
    start = datetime(day.year, day.month, day.day, hour, tzinfo=rules.TIME_ZONE)
    values = {
        "court": Court.objects.get(code="mp-01"),
        "sport": "badminton",
        "coverage": "full",
        "starts_at": start,
        "ends_at": start + timedelta(hours=1),
        "hours": 1,
        "source": Source.ONLINE,
        "status": Status.CONFIRMED,
        "price_centavos": 30000,
        "customer_name": NAME,
        "customer_email": EMAIL,
        "customer_mobile": MOBILE,
    }
    values.update(fields)
    return Booking.objects.create(reference=reference, **values)


def walk_in(code="mp-01", day=TODAY, hour=16, *, name="", is_demo=False) -> Booking:
    return holds.create_staff_booking(
        source=Source.WALK_IN,
        court=Court.objects.get(code=code),
        sport="badminton",
        coverage="full",
        half=None,
        day=day,
        start_hour=hour,
        hours=1,
        created_by=None,
        customer_name=name,
        is_demo=is_demo,
        now=NOW,
    )


def online(code="mp-02", hour=14, *, is_demo=False) -> Booking:
    """A paid online booking, made the evening before through a real hold."""
    booking = holds.create_hold(
        court=Court.objects.get(code=code),
        sport="badminton",
        coverage="full",
        day=TODAY,
        start_hour=hour,
        hours=1,
        customer=Customer(name=NAME, email=EMAIL, mobile=MOBILE),
        now=NOW - timedelta(hours=16),
    )
    Booking.objects.filter(pk=booking.pk).update(
        status=Status.CONFIRMED, payment_method="card", paid_at=NOW, is_demo=is_demo
    )
    booking.refresh_from_db()
    return booking


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


class Tags(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)


def references(html: str) -> list[str]:
    """The booking references the table lists, in order (the cards repeat them, so only the
    table's row headers are read)."""
    if 'class="table-scroll bk-table"' not in html:
        return []
    table = html.split('class="table-scroll bk-table"', 1)[1].split("</table>", 1)[0]
    return re.findall(r'<th scope="row"><a href="/dashboard/bookings/([^/]+)/', table)


def listed(client, **params) -> list[str]:
    response = client.get(URL, params)
    assert response.status_code == 200
    return references(response.content.decode())


def assert_csp_safe(html):
    tags = Tags(html).tags
    assert [attrs for tag, attrs in tags if tag == "script" and ("src", None) in attrs] == []
    assert not [
        name
        for _, attrs in tags
        for name, _ in attrs
        if name.startswith("hx-on") or name == "style"
    ]
    assert "javascript:" not in html
    scripts = [dict(attrs) for tag, attrs in tags if tag == "script"]
    assert all("src" in attrs for attrs in scripts)


# --- access -------------------------------------------------------------------------------------


@pytest.mark.django_db
class TestAccess:
    @pytest.mark.parametrize("url", [URL, detail_url("KC-T00001")])
    def test_anonymous_is_redirected_to_login(self, client, url):
        make()

        response = client.get(url)

        assert response.status_code == 302
        assert response["Location"] == "/dashboard/login/"

    def test_htmx_anonymous_gets_hx_redirect(self, client):
        response = client.get(URL, headers=HX)

        assert response["HX-Redirect"] == "/dashboard/login/"
        assert response.content == b""

    def test_bookings_is_in_the_nav(self, owner):
        html = owner.get(URL).content.decode()

        assert '<a href="/dashboard/bookings/" aria-current="page">Bookings</a>' in html
        assert html.index(">Schedule</a>") < html.index(">Bookings</a>")

    def test_page_is_csp_safe(self, viewer):
        make()

        assert_csp_safe(viewer.get(URL).content.decode())

    def test_detail_is_csp_safe(self, owner):
        make()

        assert_csp_safe(owner.get(detail_url("KC-T00001")).content.decode())


# --- search -------------------------------------------------------------------------------------


@pytest.mark.django_db
class TestSearch:
    def test_owner_finds_by_email_mobile_name_and_reference(self, owner):
        make("KC-T00001")
        make(
            "KC-T00002",
            customer_name="Ana Reyes",
            customer_email="ana@example.com",
            customer_mobile="+639990000000",
            hour=15,
        )

        assert listed(owner, q=EMAIL) == ["KC-T00001"]
        assert listed(owner, q="JUAN.CRUZ") == ["KC-T00001"]
        assert listed(owner, q="1234567") == ["KC-T00001"]
        assert listed(owner, q="dela cruz") == ["KC-T00001"]
        assert listed(owner, q="t00002") == ["KC-T00002"]

    def test_viewer_cannot_find_a_booking_by_email_or_mobile(self, viewer):
        make()

        assert listed(viewer, q=EMAIL) == []
        assert listed(viewer, q="juan.cruz") == []
        assert listed(viewer, q="example.com") == []
        assert listed(viewer, q=MOBILE) == []
        assert listed(viewer, q="1234567") == []

    def test_viewer_finds_by_name_and_reference(self, viewer):
        make()

        assert listed(viewer, q="Juan") == ["KC-T00001"]
        assert listed(viewer, q="dela cruz") == ["KC-T00001"]
        assert listed(viewer, q="KC-T00001") == ["KC-T00001"]

    def test_no_match_says_so(self, owner):
        html = owner.get(URL, {"q": "nobody"}).content.decode()

        assert "No bookings match." in html

    def test_a_nul_byte_in_the_search_does_not_crash(self, owner):
        make()

        assert listed(owner, q="a\x00b") == []
        assert listed(owner, q="\x00") == ["KC-T00001"]

    def test_search_is_capped_at_60_characters(self):
        params = queries.parse_list_params(QueryDict("q=" + "x" * 200))

        assert params.q == "x" * 60


# --- masking ------------------------------------------------------------------------------------


@pytest.mark.django_db
class TestMasking:
    def test_viewer_list_masks_the_customer(self, viewer):
        make()

        html = viewer.get(URL).content.decode()

        assert EMAIL not in html and MOBILE not in html and "juan.cruz" not in html
        assert "Dela Cruz" not in html
        assert "Juan D." in html
        assert "j•••@example.com" in html

    def test_viewer_detail_masks_the_customer(self, viewer):
        make()

        html = viewer.get(detail_url("KC-T00001")).content.decode()

        assert EMAIL not in html and MOBILE not in html and "Dela Cruz" not in html
        assert "Juan D." in html
        assert "j•••@example.com" in html
        assert "•••67" in html

    def test_owner_sees_the_customer_raw(self, owner):
        make()

        for url in (URL, detail_url("KC-T00001")):
            html = owner.get(url).content.decode()
            assert EMAIL in html
        assert NAME in owner.get(detail_url("KC-T00001")).content.decode()
        assert MOBILE in owner.get(detail_url("KC-T00001")).content.decode()

    def test_query_layer_masks_before_the_template(self):
        make()
        params = queries.parse_list_params(QueryDict(""))

        (row,) = queries.list_bookings(role=Role.VIEWER, params=params).rows
        detail = queries.get_booking(role=Role.VIEWER, reference="KC-T00001")

        assert (row.name, row.email) == ("Juan D.", "j•••@example.com")
        assert (detail.name, detail.email, detail.mobile) == (
            "Juan D.",
            "j•••@example.com",
            "•••67",
        )
        (raw,) = queries.list_bookings(role=Role.OWNER, params=params).rows
        assert (raw.name, raw.email) == (NAME, EMAIL)

    def test_viewer_does_not_see_a_walk_ins_note_but_does_see_a_blocks(self, viewer):
        make("KC-T00001", source=Source.WALK_IN, note="Paid by cash, regular", customer_email=None)
        make(
            "KC-T00002",
            source=Source.BLOCK,
            sport=None,
            price_centavos=0,
            note="Maintenance",
            customer_name="",
            customer_email=None,
            customer_mobile=None,
            hour=15,
        )

        assert "Paid by cash" not in viewer.get(detail_url("KC-T00001")).content.decode()
        assert "Maintenance" in viewer.get(detail_url("KC-T00002")).content.decode()


# --- filters, sorts and pages -------------------------------------------------------------------


@pytest.mark.django_db
class TestFilters:
    def test_status_filter(self, owner):
        make("KC-T00001", status=Status.CONFIRMED)
        make("KC-T00002", status=Status.CANCELLED, hour=15)
        make("KC-T00003", status=Status.NEEDS_REFUND, hour=16)

        assert listed(owner, status="cancelled") == ["KC-T00002"]
        assert listed(owner, status="needs_refund") == ["KC-T00003"]
        assert len(listed(owner)) == 3

    def test_sport_filter(self, owner):
        make("KC-T00001", sport="badminton")
        make("KC-T00002", sport="pickleball", hour=15)

        assert listed(owner, sport="pickleball") == ["KC-T00002"]

    def test_source_filter(self, owner):
        make("KC-T00001")
        make("KC-T00002", source=Source.WALK_IN, hour=15)
        make("KC-T00003", source=Source.BLOCK, sport=None, price_centavos=0, hour=16)

        assert listed(owner, source="walk_in") == ["KC-T00002"]
        assert listed(owner, source="block") == ["KC-T00003"]
        assert len(listed(owner)) == 3

    def test_filters_combine(self, owner):
        make("KC-T00001", sport="badminton", status=Status.CANCELLED)
        make("KC-T00002", sport="badminton", hour=15)
        make("KC-T00003", sport="pickleball", status=Status.CANCELLED, hour=16)

        assert listed(owner, sport="badminton", status="cancelled") == ["KC-T00001"]

    def test_date_range_is_by_manila_day_and_inclusive(self, owner):
        make("KC-T00001", day=TODAY - timedelta(days=2), hour=7)
        make("KC-T00002", day=TODAY - timedelta(days=1), hour=23)  # 23:00-24:00 Manila.
        make("KC-T00003", day=TODAY, hour=0)  # Midnight Manila is 16:00 UTC the day before.
        make("KC-T00004", day=TODAY + timedelta(days=1), hour=8)

        both = listed(owner, **{"from": TODAY.isoformat(), "to": TODAY.isoformat()})
        assert both == ["KC-T00003"]
        assert listed(owner, **{"from": (TODAY - timedelta(days=1)).isoformat()}) == [
            "KC-T00004",
            "KC-T00003",
            "KC-T00002",
        ]
        assert listed(owner, to=(TODAY - timedelta(days=1)).isoformat()) == [
            "KC-T00002",
            "KC-T00001",
        ]

    def test_sorts(self, owner):
        early = make("KC-T00001", hour=8, price_centavos=50000)
        late = make("KC-T00002", hour=20, price_centavos=10000)
        mid = make("KC-T00003", hour=12, price_centavos=30000)
        for booking, created in ((early, 3), (late, 1), (mid, 2)):
            Booking.objects.filter(pk=booking.pk).update(created_at=NOW - timedelta(days=created))

        assert listed(owner) == ["KC-T00002", "KC-T00003", "KC-T00001"]  # -starts_at, the default.
        assert listed(owner, sort="starts_at") == ["KC-T00001", "KC-T00003", "KC-T00002"]
        assert listed(owner, sort="-created_at") == ["KC-T00002", "KC-T00003", "KC-T00001"]
        assert listed(owner, sort="-price_centavos") == ["KC-T00001", "KC-T00003", "KC-T00002"]

    def test_invalid_values_fall_back_to_their_defaults(self, owner):
        make("KC-T00001")
        params = queries.parse_list_params(
            QueryDict("status=bogus&sport=golf&source=x&from=2026-13-40&to=junk&sort=hax&page=abc")
        )

        assert params == queries.ListParams(
            q="", status=None, sport=None, source=None, date_from=None, date_to=None,
            sort="-starts_at", page=1,
        )  # fmt: skip
        assert listed(
            owner, status="bogus", sport="golf", source="x", sort="hax", page="abc", to="junk"
        ) == ["KC-T00001"]

    @pytest.mark.parametrize("value", ["0", "-3", "abc", "", "1.5", "9" * 5000])
    def test_a_bad_page_is_page_one(self, value):
        assert (
            queries.parse_list_params(QueryDict(f"page={value}")).page == 1 or value == "9" * 5000
        )

    def test_out_of_range_dates_are_ignored(self, owner):
        make()

        assert listed(owner, **{"from": "0001-01-01", "to": "9999-12-31"}) == ["KC-T00001"]


@pytest.mark.django_db
class TestPagination:
    @pytest.fixture(autouse=True)
    def thirty(self):
        for number in range(30):
            make(f"KC-T{number:05d}", day=TODAY - timedelta(days=number))

    def test_page_one_has_25_and_page_two_the_rest(self, owner):
        first = listed(owner)
        second = listed(owner, page=2)

        assert len(first) == 25 and len(second) == 5
        assert not set(first) & set(second)
        html = owner.get(URL, {"page": 2}).content.decode()
        assert "Showing 26–30 of 30 bookings." in html
        assert "Page 2 of 2" in html

    def test_bad_page_shows_page_one(self, owner):
        assert listed(owner, page="abc") == listed(owner)
        assert listed(owner, page=0) == listed(owner)
        assert listed(owner, page=-4) == listed(owner)

    def test_a_page_past_the_end_shows_the_last(self, owner):
        assert listed(owner, page=99) == listed(owner, page=2)

    def test_pagination_links_are_real_hrefs_with_hx_get(self, owner):
        html = owner.get(URL, {"status": "confirmed", "page": 1}).content.decode()

        link = "/dashboard/bookings/?status=confirmed&amp;page=2"
        assert f'href="{link}"' in html and f'hx-get="{link}"' in html
        assert 'hx-target="#results"' in html and 'hx-push-url="true"' in html
        assert "Previous" not in html

    def test_a_single_page_has_no_pager(self, owner):
        assert 'class="pager"' not in owner.get(URL, {"status": "cancelled"}).content.decode()

    def test_detail_links_carry_the_lists_query_string(self, owner):
        html = owner.get(
            URL, {"status": "confirmed", "sort": "starts_at", "page": 2}
        ).content.decode()

        assert (
            'href="/dashboard/bookings/KC-T00004/?status=confirmed&amp;sort=starts_at&amp;page=2"'
            in html
        )

    def test_the_filter_form_is_a_get_form_with_htmx(self, owner):
        html = owner.get(URL).content.decode()

        form = html.split('<form class="card filters"', 1)[1].split(">", 1)[0]
        assert 'method="get"' in form and 'action="/dashboard/bookings/"' in form
        assert 'hx-get="/dashboard/bookings/"' in form
        assert 'hx-trigger="change, keyup changed delay:300ms from:#q"' in form
        assert 'hx-target="#results"' in form and 'hx-push-url="true"' in form


# --- htmx ---------------------------------------------------------------------------------------


@pytest.mark.django_db
class TestHtmx:
    def test_an_htmx_request_returns_only_the_results_partial(self, owner):
        make()

        full = owner.get(URL).content.decode()
        partial = owner.get(URL, headers=HX).content.decode()

        assert "<html" in full and 'name="q"' in full
        assert "<html" not in partial and 'name="q"' not in partial
        assert "dash-nav" not in partial
        assert "Showing 1–1 of 1 booking." in partial
        assert references(partial) == ["KC-T00001"]

    def test_a_history_restore_gets_the_whole_page(self, owner):
        html = owner.get(URL, headers={**HX, "HX-History-Restore-Request": "true"}).content.decode()

        assert "<html" in html

    def test_partial_is_masked_for_the_viewer(self, viewer):
        make()

        html = viewer.get(URL, {"q": "juan"}, headers=HX).content.decode()

        assert "Juan D." in html and EMAIL not in html and MOBILE not in html


# --- the list's rows ----------------------------------------------------------------------------


@pytest.mark.django_db
class TestRows:
    def test_status_badges_source_tags_and_demo_tag(self, owner):
        make("KC-T00001", is_demo=True)
        make("KC-T00002", status=Status.NEEDS_REFUND, source=Source.WALK_IN, hour=15)

        html = owner.get(URL).content.decode()

        assert "badge badge-confirmed" in html and "badge badge-needs_refund" in html
        assert "tag tag-online" in html and "tag tag-walk_in" in html
        assert html.count('tag tag-demo">Demo') == 2  # The table row and the card.
        assert html.count("Demo</span>") == 2

    def test_a_block_row_has_no_price_or_customer(self, owner):
        make(
            source=Source.BLOCK,
            sport=None,
            price_centavos=0,
            note="Maintenance",
            customer_name="",
            customer_email=None,
            customer_mobile=None,
        )

        (row,) = queries.list_bookings(
            role=Role.OWNER, params=queries.parse_list_params(QueryDict(""))
        ).rows

        assert (row.price, row.name, row.email, row.sport) == ("", "", "", "")
        assert "tag tag-block" in owner.get(URL).content.decode()

    def test_the_table_and_the_cards_both_render(self, owner):
        make()

        html = owner.get(URL).content.decode()

        assert 'class="table-scroll bk-table"' in html and 'class="bk-cards"' in html
        assert html.count('href="/dashboard/bookings/KC-T00001/"') == 2


# --- the detail page ----------------------------------------------------------------------------


@pytest.mark.django_db
class TestDetail:
    def test_unknown_reference_is_404(self, owner):
        assert owner.get(detail_url("KC-NOPE00")).status_code == 404

    def test_shows_everything_for_the_owner(self, owner):
        make(
            payment_method="card",
            fee_centavos=1500,
            net_centavos=28500,
            paid_at=NOW,
            consent_at=NOW - timedelta(days=1),
            hours=2,
        )

        html = owner.get(detail_url("KC-T00001")).content.decode()

        for text in (
            "Booking KC-T00001",
            "Mon 2 Nov 2026, 2:00 PM - 3:00 PM",
            "Mobile",
            "card",
            "₱15",
            "₱285",
            "2 Nov 2026, 12:00 PM",
            "Consent given",
            "1 Nov 2026, 12:00 PM",
        ):
            assert text in html

    def test_the_query_layer_returns_payment_and_consent(self):
        make(
            payment_method="card",
            fee_centavos=1500,
            net_centavos=28500,
            paid_at=NOW,
            consent_at=NOW,
        )

        detail = queries.get_booking(role=Role.OWNER, reference="KC-T00001")

        assert (detail.payment_method, detail.fee, detail.net) == ("card", "₱15", "₱285")
        assert detail.paid_at == "2 Nov 2026, 12:00 PM" and detail.consent_at == detail.paid_at
        assert detail.can_cancel and not detail.anonymized

    def test_back_link_restores_the_lists_query(self, owner):
        make()

        html = owner.get(
            detail_url("KC-T00001"), {"status": "confirmed", "q": "juan", "page": 3, "evil": "<x>"}
        ).content.decode()

        assert '<a href="/dashboard/bookings/?q=juan&amp;status=confirmed&amp;page=3">' in html
        assert "evil" not in html

    def test_back_link_without_a_query(self, owner):
        make()

        html = owner.get(detail_url("KC-T00001")).content.decode()

        assert '<a href="/dashboard/bookings/">‹ All bookings</a>' in html

    def test_needs_refund_callout(self, owner):
        make(status=Status.NEEDS_REFUND)

        html = owner.get(detail_url("KC-T00001")).content.decode()

        assert "needs-refund" not in html
        assert "Refund it in the PayMongo dashboard" in html
        assert "Cancel booking" not in html  # It can no longer be cancelled.

    def test_no_callout_for_a_confirmed_booking(self, owner):
        make()

        assert (
            "Refund it in the PayMongo" not in owner.get(detail_url("KC-T00001")).content.decode()
        )

    def test_anonymized_booking_shows_the_note_and_no_contact_details(self, owner):
        make(
            customer_name="",
            customer_email=None,
            customer_mobile=None,
            anonymized_at=NOW,
            status=Status.CONFIRMED,
        )

        html = owner.get(detail_url("KC-T00001")).content.decode()

        assert "Anonymized" in html
        assert "<dt>Name</dt>" not in html and "<dt>Email</dt>" not in html
        assert "<dt>Mobile</dt>" not in html and "<dt>Consent given</dt>" not in html

    def test_anonymized_booking_in_the_list_has_no_customer(self, viewer):
        make(customer_name="", customer_email=None, customer_mobile=None, anonymized_at=NOW)

        (row,) = queries.list_bookings(
            role=Role.VIEWER, params=queries.parse_list_params(QueryDict(""))
        ).rows

        assert (row.name, row.email, row.mobile) == ("", "", "")
        assert viewer.get(URL).status_code == 200

    def test_a_walk_in_is_paid_in_cash(self, owner):
        booking = walk_in()

        html = owner.get(detail_url(booking.reference)).content.decode()

        assert "Cash at the venue" in html

    def test_detail_has_a_panel_for_refusals(self, owner):
        make()

        assert 'id="panel"' in owner.get(detail_url("KC-T00001")).content.decode()


@pytest.mark.django_db
class TestCancelButton:
    def test_absent_for_the_viewer_on_a_real_online_booking(self, viewer):
        booking = online()

        html = viewer.get(detail_url(booking.reference)).content.decode()

        assert "Cancel booking" not in html
        assert cancel_url(booking.reference) not in html

    def test_present_for_the_viewer_on_a_demo_online_booking(self, viewer):
        booking = online(is_demo=True)

        html = viewer.get(detail_url(booking.reference)).content.decode()

        assert "Cancel booking" in html
        assert f'action="{cancel_url(booking.reference)}"' in html
        assert 'name="return" value="detail"' in html
        assert 'name="csrfmiddlewaretoken"' in html

    def test_present_for_the_viewer_on_a_walk_in(self, viewer):
        assert "Cancel booking" in viewer.get(detail_url(walk_in().reference)).content.decode()

    def test_present_for_the_owner_on_a_real_online_booking(self, owner):
        booking = online()

        assert "Cancel booking" in owner.get(detail_url(booking.reference)).content.decode()

    def test_absent_once_cancelled(self, owner):
        booking = walk_in()
        Booking.objects.filter(pk=booking.pk).update(status=Status.CANCELLED)

        assert "Cancel booking" not in owner.get(detail_url(booking.reference)).content.decode()


@pytest.mark.django_db
class TestCancelFromDetail:
    def test_htmx_cancel_redirects_back_to_the_detail_page(self, owner):
        booking = walk_in()

        response = owner.post(cancel_url(booking.reference), {"return": "detail"}, headers=HX)

        assert response.status_code == 200
        assert response["HX-Redirect"] == detail_url(booking.reference)
        assert response.content == b""
        booking.refresh_from_db()
        assert booking.status == Status.CANCELLED

    def test_plain_post_is_a_303_to_the_detail_page(self, owner):
        booking = walk_in()

        response = owner.post(cancel_url(booking.reference), {"return": "detail"})

        assert response.status_code == 303
        assert response["Location"] == detail_url(booking.reference)
        booking.refresh_from_db()
        assert booking.status == Status.CANCELLED
        followed = owner.get(response["Location"]).content.decode()
        assert "Cancelled" in followed and "Cancel booking" not in followed

    def test_without_return_it_still_answers_with_the_grid(self, owner):
        booking = walk_in()

        response = owner.post(cancel_url(booking.reference), headers=HX)

        assert response.status_code == 200
        assert "HX-Redirect" not in response
        assert 'id="toast"' in response.content.decode()

    def test_an_unknown_return_value_is_ignored(self, owner):
        booking = walk_in()

        response = owner.post(cancel_url(booking.reference), {"return": "elsewhere"}, headers=HX)

        assert "HX-Redirect" not in response

    def test_the_viewer_is_still_refused_on_a_real_online_booking(self, viewer):
        booking = online()

        response = viewer.post(cancel_url(booking.reference), {"return": "detail"}, headers=HX)

        assert response.status_code == 403
        assert "HX-Redirect" not in response
        assert response["HX-Retarget"] == "#panel"
        booking.refresh_from_db()
        assert booking.status == Status.CONFIRMED

    def test_the_viewers_write_limit_still_applies(self, viewer):
        booking = walk_in(is_demo=True)
        for _ in range(views.WRITE_LIMIT):
            assert ratelimit.hit(
                "staff_write",
                "127.0.0.1",
                limit=views.WRITE_LIMIT,
                window_seconds=views.WRITE_WINDOW_SECONDS,
            )

        response = viewer.post(cancel_url(booking.reference), {"return": "detail"}, headers=HX)

        assert response.status_code == 429
        assert "HX-Redirect" not in response
        booking.refresh_from_db()
        assert booking.status == Status.CONFIRMED

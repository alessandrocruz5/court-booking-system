from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group, User
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import path

from accounts.decorators import staff_required
from accounts.roles import (
    Role,
    can_cancel,
    can_check_in,
    can_create_staff_booking,
    can_see_personal_data,
)
from core.http import client_ip


@staff_required
def _staff_view(request):
    return HttpResponse(request.staff_role)


def _open_view(request):
    return HttpResponse("open")


# This module is its own urlconf (`@pytest.mark.urls(__name__)`).
urlpatterns = [
    path("dashboard/login/", _open_view),
    path("dashboard/plain/", _open_view),
    path("staff/", _staff_view),
]

LOGIN = "/dashboard/login/"
HTMX = {"HTTP_HX_REQUEST": "true"}
UNKNOWN = "0.0.0.0"  # noqa: S104 (the fallback rate-limit key)


def _user(username, *groups, is_active=True):
    user = User.objects.create_user(username=username, password="x" * 16, is_active=is_active)
    for name in groups:
        user.groups.add(Group.objects.get_or_create(name=name)[0])
    return user


@pytest.mark.django_db
@pytest.mark.urls(__name__)
class TestStaffRequired:
    def test_anonymous_is_redirected_to_login(self, client):
        response = client.get("/staff/")

        assert response.status_code == 302
        assert response["Location"] == LOGIN

    def test_htmx_anonymous_gets_hx_redirect(self, client):
        response = client.get("/staff/", **HTMX)

        assert response.status_code == 200
        assert response.content == b""
        assert response["HX-Redirect"] == LOGIN

    def test_user_in_no_group_is_redirected(self, client):
        client.force_login(_user("nobody@example.com"))

        assert client.get("/staff/").status_code == 302

    @pytest.mark.parametrize("role", [Role.VIEWER, Role.OWNER])
    def test_role_member_gets_the_view_with_staff_role(self, client, role):
        client.force_login(_user(f"{role}@example.com", role))

        response = client.get("/staff/")

        assert response.status_code == 200
        assert response.content.decode() == role

    def test_owner_wins_when_in_both_groups(self, client):
        client.force_login(_user("both@example.com", Role.VIEWER, Role.OWNER))

        assert client.get("/staff/").content.decode() == Role.OWNER

    def test_inactive_user_is_redirected(self, client):
        client.force_login(_user("gone@example.com", Role.OWNER, is_active=False))

        assert client.get("/staff/").status_code == 302

    def test_role_of_refuses_inactive_user_even_when_loaded(self):
        # The backend already drops inactive users; role_of must refuse them on its own too.
        from accounts.roles import role_of

        assert role_of(_user("gone@example.com", Role.OWNER, is_active=False)) is None

    def test_responses_are_no_store(self, client):
        assert "no-store" in client.get("/staff/")["Cache-Control"]
        client.force_login(_user("viewer@example.com", Role.VIEWER))
        cache_control = client.get("/staff/")["Cache-Control"]
        assert "no-store" in cache_control
        assert "private" in cache_control


@pytest.mark.django_db
@pytest.mark.urls(__name__)
class TestMiddleware:
    def test_anonymous_dashboard_path_is_redirected(self, client):
        response = client.get("/dashboard/anything")

        assert response.status_code == 302
        assert response["Location"] == LOGIN
        assert "no-store" in response["Cache-Control"]

    def test_htmx_anonymous_dashboard_path_gets_hx_redirect(self, client):
        response = client.get("/dashboard/anything", **HTMX)

        assert response.status_code == 200
        assert response["HX-Redirect"] == LOGIN

    def test_login_page_passes(self, client):
        response = client.get(LOGIN)

        assert response.status_code == 200
        assert response.content == b"open"

    def test_authenticated_user_passes_without_a_role_check(self, client):
        # The middleware only redirects anonymous visitors; roles are the decorator's job.
        client.force_login(_user("nobody@example.com"))

        assert client.get("/dashboard/plain/").status_code == 200

    def test_paths_outside_the_dashboard_pass(self, client):
        assert client.get("/dashboardx").status_code == 404


def test_permissions_by_role():
    assert can_see_personal_data(Role.OWNER)
    assert not can_see_personal_data(Role.VIEWER)
    assert not can_see_personal_data(None)
    assert can_create_staff_booking(Role.OWNER)
    assert can_create_staff_booking(Role.VIEWER)
    assert not can_create_staff_booking(None)


NOW = datetime(2026, 11, 2, 4, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)


def _booking(
    source="online",
    status="confirmed",
    is_demo=False,
    ends_at=LATER,
    starts_at=NOW,
    checked_in_at=None,
):
    return SimpleNamespace(
        source=source,
        status=status,
        is_demo=is_demo,
        ends_at=ends_at,
        starts_at=starts_at,
        checked_in_at=checked_in_at,
    )


@pytest.mark.parametrize(
    ("role", "booking", "allowed"),
    [
        (Role.OWNER, _booking(), True),
        (Role.OWNER, _booking(status="pending"), True),
        (Role.VIEWER, _booking(), False),
        (Role.VIEWER, _booking(is_demo=True), True),
        (Role.VIEWER, _booking(source="walk_in"), True),
        (Role.VIEWER, _booking(source="block"), True),
        (Role.OWNER, _booking(status="cancelled"), False),
        (Role.VIEWER, _booking(source="walk_in", status="cancelled"), False),
        (Role.OWNER, _booking(status="expired"), False),
        (None, _booking(source="walk_in"), False),
        # The viewer may cancel only what hasn't ended; the owner may cancel either.
        (Role.VIEWER, _booking(source="walk_in", ends_at=NOW - timedelta(minutes=1)), False),
        (Role.VIEWER, _booking(source="walk_in", ends_at=NOW), False),
        (Role.VIEWER, _booking(is_demo=True, ends_at=NOW - timedelta(hours=1)), False),
        (Role.VIEWER, _booking(source="block", ends_at=NOW - timedelta(hours=1)), False),
        (Role.VIEWER, _booking(source="walk_in", ends_at=NOW + timedelta(minutes=1)), True),
        (Role.OWNER, _booking(ends_at=NOW - timedelta(hours=1)), True),
    ],
)
def test_cancel_permissions(role, booking, allowed):
    assert can_cancel(role, booking, now=NOW) is allowed


# NOW is 12:00 in Manila; 16:00 UTC the same UTC day is already tomorrow there.
MANILA_TOMORROW = datetime(2026, 11, 2, 16, tzinfo=UTC)


@pytest.mark.parametrize(
    ("role", "booking", "allowed"),
    [
        (Role.OWNER, _booking(), True),
        (Role.OWNER, _booking(source="walk_in"), True),
        (Role.OWNER, _booking(status="pending"), False),
        (Role.OWNER, _booking(status="cancelled"), False),
        (Role.OWNER, _booking(status="needs_refund"), False),
        (Role.OWNER, _booking(status="expired"), False),
        (Role.OWNER, _booking(source="block"), False),
        (Role.OWNER, _booking(checked_in_at=NOW - timedelta(minutes=5)), False),
        (Role.OWNER, _booking(ends_at=NOW), False),
        (Role.OWNER, _booking(ends_at=NOW + timedelta(minutes=1)), True),
        (
            Role.OWNER,
            _booking(starts_at=NOW + timedelta(days=1), ends_at=LATER + timedelta(days=1)),
            False,
        ),
        (
            Role.OWNER,
            _booking(starts_at=MANILA_TOMORROW, ends_at=MANILA_TOMORROW + timedelta(hours=1)),
            False,
        ),
        # The viewer: demo data or a walk-in, never a real visitor's online booking.
        (Role.VIEWER, _booking(), False),
        (Role.VIEWER, _booking(is_demo=True), True),
        (Role.VIEWER, _booking(source="walk_in"), True),
        (Role.VIEWER, _booking(source="block"), False),
        (Role.VIEWER, _booking(source="block", is_demo=True), False),
        (Role.VIEWER, _booking(is_demo=True, status="pending"), False),
        (Role.VIEWER, _booking(is_demo=True, ends_at=NOW), False),
        (Role.VIEWER, _booking(source="walk_in", checked_in_at=NOW), False),
        (None, _booking(source="walk_in"), False),
        (None, _booking(is_demo=True), False),
    ],
)
def test_check_in_permissions(role, booking, allowed):
    assert can_check_in(role, booking, now=NOW) is allowed


def _request(xff=None, remote="10.0.0.1"):
    meta = {"REMOTE_ADDR": remote}
    if xff is not None:
        meta["HTTP_X_FORWARDED_FOR"] = xff
    return RequestFactory().get("/", **meta)


@pytest.mark.parametrize(
    ("xff", "remote", "expected"),
    [
        ("1.1.1.1, 2.2.2.2", "10.0.0.1", "2.2.2.2"),
        ("2.2.2.2", "10.0.0.1", "2.2.2.2"),
        ("not-an-ip", "10.0.0.1", "10.0.0.1"),
        ("1.1.1.1, garbage", "10.0.0.1", "10.0.0.1"),
        (None, "10.0.0.1", "10.0.0.1"),
        ("garbage", "also-garbage", UNKNOWN),
        ("garbage", "", UNKNOWN),
        # IPv6: the /64, so one subscriber can't rotate through its allocation.
        ("2001:db8:1:2:aaaa::1", "10.0.0.1", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:bbbb::9", "10.0.0.1", "2001:db8:1:2::/64"),
        # IPv4-mapped IPv6 folds to the IPv4 address.
        ("::ffff:2.2.2.2", "10.0.0.1", "2.2.2.2"),
        # A zone ID is invalid, in the header and in REMOTE_ADDR.
        ("fe80::1%eth0", "10.0.0.1", "10.0.0.1"),
        ("garbage", "fe80::1%eth0", UNKNOWN),
        ("garbage", "2001:db8::5", "2001:db8::/64"),
    ],
)
def test_client_ip(xff, remote, expected):
    assert client_ip(_request(xff, remote)) == expected


def test_client_ip_without_remote_addr():
    request = RequestFactory().get("/")
    del request.META["REMOTE_ADDR"]

    assert client_ip(request) == UNKNOWN

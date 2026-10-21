import io
import logging
from datetime import UTC, datetime
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.db import OperationalError
from django.test import Client, RequestFactory
from django.views.defaults import bad_request, permission_denied, server_error

from accounts import views
from accounts.roles import Role, role_of
from bookings.management.commands import nightly
from core import ratelimit

LOGIN = "/dashboard/login/"
DEMO = "/dashboard/demo/"
LOGOUT = "/dashboard/logout/"
DASHBOARD = "/dashboard/"
BANNER = "Fictional venue · Test mode, no real payments"

OWNER_EMAIL = "owner@example.com"
VIEWER_EMAIL = "viewer@example.com"
OWNER_PASSWORD = "owner-password-0123"
VIEWER_PASSWORD = "viewer-password-0123"
# Inside one 60-second window (09:00:00–09:00:59), so a run can't straddle two.
NOW = datetime(2026, 11, 2, 9, 0, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def pinned_clock(monkeypatch):
    # Only the rate limiter's clock: sessions keep the real one.
    monkeypatch.setattr(ratelimit, "timezone", SimpleNamespace(now=lambda: NOW))


@pytest.fixture
def staff(db, monkeypatch):
    env = {
        "STAFF_OWNER_EMAIL": OWNER_EMAIL,
        "STAFF_OWNER_PASSWORD": OWNER_PASSWORD,
        "DEMO_VIEWER_EMAIL": VIEWER_EMAIL,
        "DEMO_VIEWER_PASSWORD": VIEWER_PASSWORD,
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    call_command("seed_staff", stdout=io.StringIO())
    return env


def _sign_in(client, email=OWNER_EMAIL, password=OWNER_PASSWORD, **extra):
    return client.post(LOGIN, {"email": email, "password": password}, **extra)


def _signed_in_user(client):
    user_id = client.session.get("_auth_user_id")
    return None if user_id is None else User.objects.get(pk=user_id)


class _FormFields(HTMLParser):
    """The named controls inside the form with `form_id`."""

    def __init__(self, form_id):
        super().__init__()
        self.form_id = form_id
        self.inside = False
        self.names = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.inside = attrs.get("id") == self.form_id
        elif self.inside and tag in {"input", "button", "select", "textarea"} and "name" in attrs:
            self.names.append(attrs["name"])

    def handle_endtag(self, tag):
        if tag == "form":
            self.inside = False


def _field_names(html, form_id):
    parser = _FormFields(form_id)
    parser.feed(html)
    return parser.names


class _Tags(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def _assert_csp_safe(html):
    """No inline script and no `hx-on` handler: the CSP allows scripts only from 'self'."""
    tags = _Tags(html).tags
    assert [attrs for tag, attrs in tags if tag == "script" and "src" not in attrs] == []
    assert not [name for _, attrs in tags for name in attrs if name.startswith("hx-on")]
    assert "javascript:" not in html


@pytest.mark.django_db
class TestLoginPage:
    def test_get_renders_with_banner_csp_and_no_store(self, client, staff):
        response = client.get(LOGIN)

        assert response.status_code == 200
        html = response.content.decode()
        assert BANNER in html
        assert 'aria-label="Test mode"' in html
        assert "KALARO COURTS · STAFF" in html
        assert 'autocomplete="username"' in html
        assert 'autocomplete="current-password"' in html
        assert 'href="http://localhost:3000"' in html
        assert "script-src 'self'" in response["Content-Security-Policy"]
        assert "no-store" in response["Cache-Control"]
        _assert_csp_safe(html)

    def test_known_error_key_shows_its_fixed_message(self, client, staff):
        response = client.get(LOGIN, {"error": "rate_limited"})

        assert 'role="alert"' in response.content.decode()
        assert views.ERRORS["rate_limited"] in response.content.decode()

    def test_unknown_error_key_renders_nothing_from_the_url(self, client, staff):
        response = client.get(LOGIN, {"error": "<script>alert(1)</script>"})

        html = response.content.decode()
        assert 'role="alert"' not in html
        assert "<script>" not in html
        assert "alert(1)" not in html

    def test_signed_in_staff_is_sent_to_the_dashboard(self, client, staff):
        client.force_login(User.objects.get(username=OWNER_EMAIL))

        response = client.get(LOGIN)

        assert response.status_code == 302
        assert response["Location"] == DASHBOARD

    def test_signed_in_user_without_a_role_sees_the_form(self, client, staff):
        client.force_login(User.objects.create_user("nobody@example.com", password="x" * 16))

        assert client.get(LOGIN).status_code == 200


@pytest.mark.django_db
class TestPasswordSignIn:
    def test_right_password_signs_in_and_redirects(self, client, staff):
        response = _sign_in(client)

        assert response.status_code == 302
        assert response["Location"] == DASHBOARD
        assert role_of(_signed_in_user(client)) == Role.OWNER

    def test_sign_in_rotates_the_session_key(self, client, staff):
        client.get(LOGIN)
        session = client.session
        session["probe"] = "before sign-in"
        session.save()
        old_key = session.session_key
        assert Session.objects.filter(session_key=old_key).exists()

        assert _sign_in(client)["Location"] == DASHBOARD

        assert client.session.session_key != old_key
        assert not Session.objects.filter(session_key=old_key).exists()

    def test_email_is_trimmed_and_lowercased(self, client, staff):
        response = _sign_in(client, email="  Owner@Example.COM ")

        assert response["Location"] == DASHBOARD
        assert _signed_in_user(client).username == OWNER_EMAIL

    def test_wrong_password_is_invalid(self, client, staff):
        response = _sign_in(client, password="wrong-password-0000")

        assert response.status_code == 302
        assert response["Location"] == f"{LOGIN}?error=invalid"
        assert _signed_in_user(client) is None

    def test_user_with_no_role_is_invalid(self, client, staff):
        User.objects.create_user("nobody@example.com", password="nobody-password-01")

        response = _sign_in(client, email="nobody@example.com", password="nobody-password-01")

        assert response["Location"] == f"{LOGIN}?error=invalid"
        assert _signed_in_user(client) is None

    def test_sixth_attempt_in_a_minute_is_rate_limited_even_when_right(self, client, staff):
        for _ in range(5):
            assert _sign_in(client, password="wrong")["Location"] == f"{LOGIN}?error=invalid"

        response = _sign_in(client)

        assert response["Location"] == f"{LOGIN}?error=rate_limited"
        assert _signed_in_user(client) is None
        # Another address has its own count.
        other = Client(REMOTE_ADDR="198.51.100.9")
        assert _sign_in(other)["Location"] == DASHBOARD

    def test_database_error_fails_closed(self, client, staff, monkeypatch, caplog):
        def broken(*args, **kwargs):
            raise OperationalError("connection to 10.0.0.5 failed for owner@example.com")

        monkeypatch.setattr(views, "hit", broken)

        with caplog.at_level(logging.INFO, logger="cb.auth"):
            response = _sign_in(client)

        assert response["Location"] == f"{LOGIN}?error=unavailable"
        assert _signed_in_user(client) is None
        assert [r.getMessage() for r in caplog.records if r.name == "cb.auth"] == [
            "auth.sign_in_failed error=OperationalError"
        ]

    def test_next_parameter_is_ignored(self, client, staff):
        response = client.post(
            f"{LOGIN}?next=https://evil.example",
            {"email": OWNER_EMAIL, "password": OWNER_PASSWORD, "next": "https://evil.example"},
        )

        assert response["Location"] == DASHBOARD

    def test_missing_fields_are_invalid(self, client, staff):
        assert client.post(LOGIN, {})["Location"] == f"{LOGIN}?error=invalid"

    def test_put_is_not_allowed(self, client, staff):
        assert client.put(LOGIN).status_code == 405

    def test_window_stays_within_the_nightly_prune(self):
        assert nightly.RATE_LIMIT_MAX_AGE.total_seconds() >= views.SIGN_IN_WINDOW_SECONDS


@pytest.mark.django_db
class TestDemo:
    def test_demo_signs_in_as_the_viewer(self, client, staff):
        response = client.post(DEMO)

        assert response.status_code == 302
        assert response["Location"] == DASHBOARD
        assert role_of(_signed_in_user(client)) == Role.VIEWER

    def test_demo_form_posts_only_the_csrf_token(self, client, staff):
        html = client.get(LOGIN).content.decode()

        assert _field_names(html, "demo-form") == ["csrfmiddlewaretoken"]
        assert VIEWER_PASSWORD not in html
        assert VIEWER_EMAIL not in html

    def test_missing_env_disables_the_button_and_refuses(self, client, staff, monkeypatch, caplog):
        monkeypatch.delenv("DEMO_VIEWER_PASSWORD")

        html = client.get(LOGIN).content.decode()
        assert 'disabled aria-describedby="demo-note"' in html
        assert "The demo isn't set up on this server yet." in html

        with caplog.at_level(logging.INFO, logger="cb.auth"):
            response = client.post(DEMO)

        assert response["Location"] == f"{LOGIN}?error=demo_unavailable"
        assert _signed_in_user(client) is None
        assert "auth.demo_unavailable reason=env_missing" in caplog.messages

    def test_env_that_disagrees_with_the_seed_is_credentials_rejected(
        self, client, staff, monkeypatch, caplog
    ):
        monkeypatch.setenv("DEMO_VIEWER_PASSWORD", "not-the-seeded-password")

        with caplog.at_level(logging.INFO, logger="cb.auth"):
            response = client.post(DEMO)

        assert response["Location"] == f"{LOGIN}?error=demo_unavailable"
        assert "auth.demo_unavailable reason=credentials_rejected" in caplog.messages

    def test_demo_shares_the_sign_in_rate_limit(self, client, staff):
        for _ in range(5):
            _sign_in(client, password="wrong")

        assert client.post(DEMO)["Location"] == f"{LOGIN}?error=rate_limited"

    def test_get_is_not_allowed(self, client, staff):
        assert client.get(DEMO).status_code == 405

    def test_csrf_token_is_required(self, staff):
        strict = Client(enforce_csrf_checks=True)

        assert strict.post(DEMO).status_code == 403
        assert _signed_in_user(strict) is None


@pytest.mark.django_db
class TestLogout:
    def test_get_is_not_allowed(self, client, staff):
        client.force_login(User.objects.get(username=OWNER_EMAIL))

        assert client.get(LOGOUT).status_code == 405
        assert _signed_in_user(client) is not None

    def test_post_ends_the_session(self, client, staff):
        _sign_in(client)
        session_key = client.session.session_key

        response = client.post(LOGOUT)

        assert response.status_code == 302
        assert response["Location"] == LOGIN
        assert _signed_in_user(client) is None
        assert not Session.objects.filter(session_key=session_key).exists()


@pytest.mark.django_db
def test_logs_never_carry_the_email_password_or_ip(client, staff, monkeypatch, caplog):
    with caplog.at_level(logging.INFO):
        _sign_in(client, password="wrong-password-0000")
        _sign_in(client)
        client.post(LOGOUT)
        client.post(DEMO)
        monkeypatch.setenv("DEMO_VIEWER_PASSWORD", "not-the-seeded-password")
        client.post(DEMO)
        for _ in range(3):
            _sign_in(client, password="wrong-password-0000")

    messages = [record.getMessage() for record in caplog.records]
    assert "auth.sign_in_rejected reason=invalid_credentials" in messages
    assert "auth.sign_in_rejected reason=rate_limited" in messages
    text = "\n".join(messages).lower()
    for secret in (OWNER_EMAIL, VIEWER_EMAIL, "@example.com", OWNER_PASSWORD, "127.0.0.1"):
        assert secret not in text


@pytest.mark.django_db
def test_unknown_page_is_a_404_with_the_banner(client):
    response = client.get("/no-such-page")

    assert response.status_code == 404
    html = response.content.decode()
    assert BANNER in html
    assert "Page not found" in html
    assert 'href="/dashboard/"' in html
    assert "no-such-page" not in html
    _assert_csp_safe(html)


def test_server_error_page_has_the_banner():
    response = server_error(RequestFactory().get("/"))

    assert response.status_code == 500
    html = response.content.decode()
    assert BANNER in html
    _assert_csp_safe(html)


@pytest.mark.parametrize(
    ("view", "status"),
    [(bad_request, 400), (permission_denied, 403)],
)
def test_bad_request_and_forbidden_pages_have_the_banner(view, status):
    response = view(RequestFactory().get("/"), Exception("<script>secret</script>"))

    assert response.status_code == status
    html = response.content.decode()
    assert BANNER in html
    assert "secret" not in html


@pytest.mark.django_db
def test_csrf_failure_page_has_the_banner(staff):
    strict = Client(enforce_csrf_checks=True)
    response = strict.post(LOGIN, {"email": OWNER_EMAIL, "password": OWNER_PASSWORD})

    assert response.status_code == 403
    html = response.content.decode()
    assert BANNER in html
    assert "This form has expired" in html
    assert "CSRF" not in html

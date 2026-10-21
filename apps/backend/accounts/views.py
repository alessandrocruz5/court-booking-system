"""Staff sign-in (`/dashboard/login/`), the owner demo button (`/dashboard/demo/`) and sign-out.

There is no sign-up: accounts come only from `manage.py seed_staff`. Both sign-in paths share one
rate limit, 5 attempts per minute per client IP, counted in Postgres (`core.ratelimit`), and fail
closed when the database is down. The demo credentials live only in the server's env: the demo
form posts nothing but its CSRF token. The query string is only ever a key into `ERRORS`, and a
successful sign-in always lands on the dashboard (no `next`, so no open redirect).
Logs carry reasons and error classes only, never an email, a password or an IP (RA 10173).
"""

import logging

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.db import DatabaseError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from config.env import env_str
from core.http import client_ip
from core.ratelimit import hit

from .roles import role_of

logger = logging.getLogger("cb.auth")

# Must stay within the nightly prune's `RATE_LIMIT_MAX_AGE` (10 minutes).
SIGN_IN_LIMIT = 5
SIGN_IN_WINDOW_SECONDS = 60

ERRORS = {
    "invalid": "That email and password don't match a staff account.",
    "rate_limited": "Too many sign-in attempts. Wait a minute, then try again.",
    "unavailable": "Sign-in isn't available right now. Try again in a moment.",
    "demo_unavailable": "The demo isn't available right now. Try again later.",
}


def _demo_credentials() -> tuple[str, str] | None:
    """The viewer's email and password from env, read per call; None when either is unset.
    Stripped like `seed_staff` strips them, so the two always agree."""
    email = env_str("DEMO_VIEWER_EMAIL")
    password = env_str("DEMO_VIEWER_PASSWORD")
    if not email or not password:
        return None
    return email, password


def _sign_in(request, email: str, password: str) -> str:
    """Rate-limit, authenticate and log in. Returns `signed_in`, `invalid`, `rate_limited` or
    `unavailable`. A user with no role is `invalid`, so the page can't confirm an account exists."""
    try:
        if not hit(
            "staff_sign_in",
            client_ip(request),
            limit=SIGN_IN_LIMIT,
            window_seconds=SIGN_IN_WINDOW_SECONDS,
        ):
            logger.warning("auth.sign_in_rejected reason=rate_limited")
            return "rate_limited"
        user = authenticate(request, username=email.strip().lower(), password=password)
        if user is None or role_of(user) is None:
            logger.warning("auth.sign_in_rejected reason=invalid_credentials")
            return "invalid"
        login(request, user)  # Rotates the session key.
    except DatabaseError as error:
        logger.error("auth.sign_in_failed error=%s", type(error).__name__)
        return "unavailable"
    return "signed_in"


def _redirect_for(outcome: str):
    if outcome == "signed_in":
        return redirect(settings.LOGIN_REDIRECT_URL)
    return redirect(f"{settings.LOGIN_URL}?error={outcome}")


@never_cache
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "POST":
        outcome = _sign_in(request, request.POST.get("email", ""), request.POST.get("password", ""))
        return _redirect_for(outcome)
    if role_of(request.user) is not None:
        return redirect(settings.LOGIN_REDIRECT_URL)
    context = {
        # `error` only picks one of the fixed messages: nothing from the URL is rendered.
        "error_message": ERRORS.get(request.GET.get("error", "")),
        "demo_available": _demo_credentials() is not None,
        "site_url": settings.SITE_URL,
    }
    return render(request, "accounts/login.html", context)


@never_cache
@require_POST
def demo_view(request):
    """Sign in as the demo viewer with the server's credentials, through the same rate limit."""
    credentials = _demo_credentials()
    if credentials is None:
        logger.error("auth.demo_unavailable reason=env_missing")
        return _redirect_for("demo_unavailable")
    outcome = _sign_in(request, *credentials)
    if outcome == "invalid":
        # The env and the seeded account disagree: re-run `seed_staff` with the same values.
        logger.error("auth.demo_unavailable reason=credentials_rejected")
        return _redirect_for("demo_unavailable")
    return _redirect_for(outcome)


@never_cache
@require_POST
def logout_view(request):
    logout(request)
    return redirect(settings.LOGIN_URL)

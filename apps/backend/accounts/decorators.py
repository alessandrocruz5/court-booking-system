"""`@staff_required`: the staff dashboard's real access check. Wrap every dashboard view in it.

`DashboardLoginRedirectMiddleware` only redirects anonymous visitors early; it never grants access.
"""

from functools import wraps

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.cache import add_never_cache_headers
from django.views.decorators.cache import never_cache

from .roles import role_of


def login_redirect(request) -> HttpResponse:
    """Send the visitor to the sign-in page. An HTMX request gets `HX-Redirect` instead, so the
    login page isn't swapped into a partial."""
    if request.headers.get("HX-Request") == "true":
        response = HttpResponse(status=200)
        response["HX-Redirect"] = settings.LOGIN_URL
    else:
        response = redirect(settings.LOGIN_URL)
    add_never_cache_headers(response)
    return response


def staff_required(view):
    """Allow only an active user in the `owner` or `viewer` group, and set `request.staff_role`.
    Every response, the redirect included, is sent with `Cache-Control: no-store, private`."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        role = role_of(request.user)
        if role is None:
            return login_redirect(request)
        request.staff_role = role
        return view(request, *args, **kwargs)

    return never_cache(wrapper)

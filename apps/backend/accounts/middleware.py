"""Redirects anonymous visitors away from the staff dashboard early. It ONLY redirects.

`@staff_required` on each view is the real check: this middleware can't see roles, a change in
middleware order would silently disable it, and HTMX partials need the decorator's own response.
Place it after `AuthenticationMiddleware`, which sets `request.user`.
"""

from .decorators import login_redirect

_PREFIX = "/dashboard/"
_PUBLIC = frozenset({"/dashboard/login/", "/dashboard/demo/"})


class DashboardLoginRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith(_PREFIX) and path not in _PUBLIC and not request.user.is_authenticated:
            return login_redirect(request)
        return self.get_response(request)

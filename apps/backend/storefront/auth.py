"""The service-token guard for `/api/v1/*`. Only the Next.js server calls this API, with
`Authorization: Bearer <INTERNAL_API_TOKEN>`; browsers never do, so there is no CORS and no CSRF.

It fails closed: a missing or short token in settings answers 503 for every request, and the
comparison runs in constant time. Nothing here logs the header's value.
"""

import hmac
import logging
from functools import wraps
from typing import Any

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger("cb.storefront")

MIN_TOKEN_LENGTH = 32
_SCHEME = "bearer"


def json_response(data: dict[str, Any], status: int = 200) -> JsonResponse:
    """Every JSON response of the API: never cached by anything between the two services."""
    response = JsonResponse(data, status=status)
    response["Cache-Control"] = "no-store"
    return response


def _bearer_token(request) -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != _SCHEME:
        return ""
    return token.strip()


def require_service_token(view):
    """Guard a view with the shared bearer token. It also applies `csrf_exempt`, and sets
    `Cache-Control: no-store` on every response, the view's own errors (such as a 405) included."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        expected = settings.INTERNAL_API_TOKEN or ""
        if len(expected) < MIN_TOKEN_LENGTH:
            logger.error("api.unavailable reason=token_not_configured")
            return json_response({"error": "unavailable"}, status=503)

        supplied = _bearer_token(request)
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            logger.warning("api.unauthorized view=%s", view.__name__)
            return json_response({"error": "unauthorized"}, status=401)

        response = view(request, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    return csrf_exempt(wrapper)

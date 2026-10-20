"""PayMongo's signed webhook (test mode). It records a paid checkout session through the same
`confirm_payment()` as the success page, so a customer who closes the tab before the redirect is
still confirmed. Nothing is trusted before the signature on the raw body checks out, and an
unsigned request never reaches the database.

PayMongo retries any non-2xx. A verified delivery that can never succeed (another event type, a
repeat, a session from another environment, a rejected amount) gets 200 so it isn't retried; only
failures a retry can fix get 5xx.
"""

import logging
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .confirm import confirm_payment, log_error
from .env import PaymentsConfigError, get_webhook_secret
from .paymongo import PayMongoError, parse_checkout_session
from .webhook import CHECKOUT_SESSION_PAID, SIGNATURE_META_KEY, parse_event, verify_signature

logger = logging.getLogger("cb.payments")


def _reply(status: int, body: dict[str, str]) -> JsonResponse:
    return JsonResponse(body, status=status)


def _no_store(view):
    """`Cache-Control: no-store` on every response, the 405 from `require_POST` included."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    return wrapper


@csrf_exempt
@_no_store
@require_POST
def paymongo_webhook(request):
    try:
        secret = get_webhook_secret()
    except PaymentsConfigError as error:
        log_error("webhook.env_failed", error)
        return _reply(500, {"error": "unavailable"})

    raw = request.body
    check = verify_signature(
        header=request.META.get(SIGNATURE_META_KEY), raw_body=raw, secret=secret
    )
    if not check.ok:
        logger.warning("webhook.unauthorized reason=%s", check.reason)
        return _reply(401, {"error": "invalid_signature"})

    try:
        event = parse_event(raw)
    except PayMongoError as error:
        log_error("webhook.invalid_event", error)
        return _reply(400, {"error": "invalid_event"})

    # Only a live-mode webhook sends these, and none may point here: fail loudly in PayMongo's log.
    if event.livemode:
        logger.warning("webhook.rejected event_id=%s reason=livemode", event.id)
        return _reply(400, {"error": "livemode"})

    if event.type != CHECKOUT_SESSION_PAID:
        return _reply(200, {"outcome": "ignored"})

    try:
        session = parse_checkout_session(event.data)
    except PayMongoError as error:
        log_error("webhook.invalid_event", error, event_id=event.id)
        return _reply(400, {"error": "invalid_event"})

    try:
        result = confirm_payment(session)
    except Exception as error:
        log_error("webhook.confirm_failed", error, event_id=event.id, session=session.id)
        return _reply(500, {"error": "unavailable"})
    if result.status == "pending":
        logger.warning("webhook.unpaid event_id=%s session=%s", event.id, session.id)
    return _reply(200, {"outcome": result.status})

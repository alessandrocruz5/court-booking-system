"""A booking becomes paid only through `confirm_payment()`, given a checkout session the server read
from PayMongo: the success page looks it up (`check_checkout()`), and the signed webhook
(`payments.views`) receives it. Nothing in a URL is trusted.

`confirm_payment()` is idempotent and safe to run from both callers at once: the booking row is
locked and its status re-checked before the one write, so only one caller records the payment and
every caller then reports the same outcome. A payment that lands after the hold lapsed re-claims
the same slots if they are still free; otherwise the booking becomes `needs_refund`, with the
payment recorded so staff can refund it by hand.

No PayMongo call happens inside a database transaction. Logs carry booking references and
PayMongo IDs only, never customer data or an exception's text (RA 10173).
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from functools import partial

from django.db import transaction
from django.utils import timezone

from bookings.holds import reacquire, release
from bookings.models import Booking, SlotLock
from bookings.rules import Status

from .env import PaymentsConfigError
from .paymongo import CheckoutSession, Payment, PayMongoError, get_client, is_checkout_session_id

logger = logging.getLogger("cb.payments")

_SQLSTATE = re.compile(r"^[0-9A-Z]{5}$")

# A booking in one of these never changes again, so the success page needn't ask PayMongo.
FINAL_PAID = (Status.CONFIRMED, Status.NEEDS_REFUND)


def _sqlstate(error: BaseException) -> str | None:
    """The Postgres SQLSTATE under a database error (psycopg's, or Django's wrapper's cause)."""
    for candidate in (error, error.__cause__):
        code = getattr(candidate, "sqlstate", None)
        if isinstance(code, str) and _SQLSTATE.fullmatch(code):
            return code
    return None


def log_error(event: str, error: BaseException, **ids: str) -> None:
    """Log a failure without personal data: the error's class, plus PayMongo's status and codes,
    the env key at fault, or the SQLSTATE. Never `str(error)`: a database error quotes the query's
    parameters (names, emails)."""
    fields = dict(ids)
    fields["error"] = type(error).__name__
    if isinstance(error, PayMongoError):
        fields["status"] = str(error.status)
        fields["codes"] = ",".join(error.codes) or "-"
    elif isinstance(error, PaymentsConfigError):
        fields["key"] = error.key
    elif (code := _sqlstate(error)) is not None:
        fields["sqlstate"] = code
    logger.error("%s %s", event, " ".join(f"{key}={value}" for key, value in fields.items()))


@dataclass(frozen=True)
class ConfirmResult:
    # `confirmed`, `pending`, `needs_refund` or `rejected`.
    status: str
    booking: Booking | None = None
    # Set when rejected: `livemode`, `unknown_session`, `metadata_mismatch`, `amount_mismatch` or
    # `not_recorded`.
    reason: str | None = None


@dataclass(frozen=True)
class CheckResult:
    # `confirmed`, `pending`, `needs_refund`, `not_found` or `unavailable`.
    status: str
    booking: Booking | None = None


def _rejected(session: CheckoutSession, reason: str) -> ConfirmResult:
    logger.warning("payment.rejected session=%s reason=%s", session.id, reason)
    return ConfirmResult("rejected", reason=reason)


def _record(booking: Booking, payment: Payment, status: str, now: datetime) -> None:
    """Write the payment onto a booking already locked with select_for_update."""
    booking.status = status
    booking.payment_id = payment.id
    booking.payment_method = payment.method
    booking.fee_centavos = payment.fee_centavos
    booking.net_centavos = payment.net_centavos
    booking.paid_at = payment.paid_at or now
    fields = ["status", "payment_id", "payment_method", "fee_centavos", "net_centavos", "paid_at"]
    if status == Status.CONFIRMED:
        booking.hold_expires_at = None
        fields.append("hold_expires_at")
    booking.save(update_fields=[*fields, "updated_at"])


def confirm_payment(session: CheckoutSession, *, now: datetime | None = None) -> ConfirmResult:
    """Record the session's paid payment on its booking, once. The paid amount must equal the
    price snapshotted on the booking. Safe to call any number of times, from several callers at
    once."""
    now = now or timezone.now()
    if session.livemode:
        return _rejected(session, "livemode")

    booking = Booking.objects.filter(checkout_session_id=session.id).first()
    if booking is None:
        return _rejected(session, "unknown_session")
    if session.metadata.get("booking_id") != str(booking.id):
        return _rejected(session, "metadata_mismatch")
    if booking.status in FINAL_PAID:
        return ConfirmResult(booking.status, booking)

    payment = next((p for p in session.payments if p.status == "paid"), None)
    if payment is None:
        return ConfirmResult("pending", booking)
    if payment.livemode:
        return _rejected(session, "livemode")
    if payment.currency != "PHP" or payment.amount_centavos != booking.price_centavos:
        return _rejected(session, "amount_mismatch")

    with transaction.atomic():
        # Re-check under the row lock: another caller may have recorded it meanwhile.
        locked = Booking.objects.select_for_update().get(pk=booking.pk)
        if locked.status in FINAL_PAID:
            return ConfirmResult(locked.status, locked)

        if locked.status == Status.PENDING and SlotLock.objects.filter(booking=locked).exists():
            keeps_slots = True
        elif locked.status in (Status.EXPIRED, Status.PENDING):
            # The hold lapsed: a late payment. Re-claim the same slots if they're still free.
            keeps_slots = reacquire(locked, now=now)
        elif locked.status == Status.CANCELLED:
            # Paid after the hold was released.
            keeps_slots = False
        else:
            return _rejected(session, "not_recorded")

        if keeps_slots:
            _record(locked, payment, Status.CONFIRMED, now)
            logger.info("payment.confirmed ref=%s payment=%s", locked.reference, payment.id)
        else:
            # It holds nothing; drop any leftover lock so its slots stay free.
            SlotLock.objects.filter(booking=locked).delete()
            _record(locked, payment, Status.NEEDS_REFUND, now)
            logger.warning("payment.needs_refund ref=%s payment=%s", locked.reference, payment.id)
    return ConfirmResult(locked.status, locked)


def check_checkout(checkout_session_id: str | None) -> CheckResult:
    """The success page's check: find our booking for the session ID, read the session from
    PayMongo and confirm it. A session ID we don't know is never sent to PayMongo. Call it outside
    any transaction: it makes an HTTP request."""
    if not is_checkout_session_id(checkout_session_id):
        return CheckResult("not_found")
    try:
        booking = Booking.objects.filter(checkout_session_id=checkout_session_id).first()
        if booking is None:
            return CheckResult("not_found")
        if booking.status in FINAL_PAID:
            return CheckResult(booking.status, booking)

        with get_client() as client:
            session = client.retrieve_checkout_session(checkout_session_id)
        result = confirm_payment(session)
    except Exception as error:
        log_error("payment.check_failed", error, session=checkout_session_id)
        return CheckResult("unavailable")
    if result.status == "rejected":
        return CheckResult("not_found")
    return CheckResult(result.status, result.booking)


def _expire_session(checkout_session_id: str) -> None:
    """Best effort: a session left open could still take a payment, which would then need a
    refund. A failure is logged; the booking is released either way."""
    try:
        with get_client() as client:
            client.expire_checkout_session(checkout_session_id)
    except Exception as error:
        log_error("payment.expire_failed", error, session=checkout_session_id)


def release_checkout(checkout_session_id: str | None) -> str:
    """The cancel page: release a pending booking's slots, then expire its checkout session once
    the release has committed. Returns `released`, `already_paid` or `not_found`."""
    if not is_checkout_session_id(checkout_session_id):
        return "not_found"
    booking = Booking.objects.filter(checkout_session_id=checkout_session_id).first()
    if booking is None:
        return "not_found"

    with transaction.atomic():
        # Judge the locked row: a payment confirmed meanwhile must never be cancelled.
        locked = Booking.objects.select_for_update().get(pk=booking.pk)
        if locked.status in FINAL_PAID:
            return "already_paid"
        if locked.status == Status.PENDING:
            release(locked, status=Status.CANCELLED)
            # The HTTP call runs after the commit, outside the transaction.
            transaction.on_commit(partial(_expire_session, checkout_session_id))
    return "released"

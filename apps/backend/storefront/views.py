"""The storefront API (`/api/v1/*`): JSON for the Next.js server only, behind the service token.

Errors name the fields that failed, never their values. Availability is advisory; the
`SlotLock` constraint decides who gets a slot when a hold is created.

Writes take a JSON body of at most 4 KB. A booking's hold commits before PayMongo is called, and
no view here opens a transaction around a PayMongo call. Payment status comes only from
`payments.confirm`, never from the request. No response or log carries customer data (RA 10173).
"""

import ipaddress
import json
import re
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from bookings.availability import availability
from bookings.holds import Customer, SlotTaken, create_hold, release
from bookings.models import Booking, Court
from bookings.rules import SPORTS, TIME_ZONE, BookingRuleError, Coverage, Sport, Status
from core.ratelimit import hit
from payments.confirm import check_checkout, log_error, release_checkout
from payments.env import PaymentsConfigError
from payments.paymongo import PayMongoError, get_client

from .auth import json_response, require_service_token
from .payloads import availability_payload, booking_summary, catalog_payload, iso_local

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_HOURS = re.compile(r"\d{1,2}")

MAX_BODY_BYTES = 4096
_MOBILE = re.compile(r"(\+63|0)(9\d{9})")
_EMAIL_MAX_LENGTH = 254
_NAME_LENGTH = (2, 80)

# Fixed-window limits per client IP, counted in Postgres (`core.ratelimit`).
CREATE_LIMIT = 5
LOOKUP_LIMIT = 10
WINDOW_SECONDS = 600
# Unexpired pending holds one email may have before another create is refused.
MAX_ACTIVE_HOLDS = 2


@require_service_token
@require_GET
def catalog(request):
    return json_response(catalog_payload())


def _parse_date(value: str | None) -> date | None:
    if value is None or not _ISO_DATE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@require_service_token
@require_GET
def availability_view(request):
    params = request.GET
    day = _parse_date(params.get("date"))
    sport = params.get("sport")
    coverage = params.get("coverage", Coverage.FULL)
    raw_hours = params.get("hours", "1")

    fields = []
    if day is None:
        fields.append("date")
    if sport not in SPORTS:
        fields.append("sport")
    if coverage not in Coverage.values:
        fields.append("coverage")
    if not _HOURS.fullmatch(raw_hours):
        fields.append("hours")
    if fields:
        return json_response({"error": "invalid_request", "fields": fields}, status=400)

    # The range of `hours`, the coverage per sport and the booking window are booking rules.
    hours = int(raw_hours)
    try:
        courts = availability(day=day, sport=sport, coverage=coverage, hours=hours)
    except BookingRuleError as error:
        return json_response({"error": error.code}, status=400)
    return json_response(availability_payload(day, sport, coverage, hours, courts))


class _BadBody(Exception):
    def __init__(self, response):
        super().__init__()
        self.response = response


def _json_body(request) -> dict:
    """The request's JSON object. Raises `_BadBody` with a 413 past 4 KB, or a 400 when the body
    isn't a JSON object. The body is never echoed or logged."""
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = 0
    if declared > MAX_BODY_BYTES or len(request.body) > MAX_BODY_BYTES:
        raise _BadBody(json_response({"error": "too_large"}, status=413))
    try:
        data = json.loads(request.body)
    except ValueError, RecursionError:
        data = None
    if not isinstance(data, dict):
        raise _BadBody(json_response({"error": "invalid_request", "fields": ["body"]}, status=400))
    return data


def _invalid(fields: list[str]):
    return json_response({"error": "invalid_request", "fields": fields}, status=400)


def _is_int(value) -> bool:
    # bool is an int subclass; JSON true is not an hour.
    return type(value) is int


def _client_ip(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def _text(value) -> str | None:
    """A trimmed string, or None. Postgres rejects NUL in text, so a NUL is invalid input rather
    than a database error."""
    if not isinstance(value, str) or "\x00" in value:
        return None
    return value.strip()


def _name(value) -> str | None:
    name = _text(value)
    if name is None:
        return None
    low, high = _NAME_LENGTH
    return name if low <= len(name) <= high else None


def _email(value) -> str | None:
    email = _text(value)
    if email is None:
        return None
    email = email.lower()
    if not email or len(email) > _EMAIL_MAX_LENGTH:
        return None
    try:
        EmailValidator()(email)
    except ValidationError:
        return None
    return email


def _mobile(value) -> str | None:
    """A Philippine mobile number, normalized to `+639XXXXXXXXX`."""
    if not isinstance(value, str):
        return None
    match = _MOBILE.fullmatch(value.strip())
    return None if match is None else "+63" + match.group(2)


def _hour_label(hour: int) -> tuple[int, str]:
    return hour % 12 or 12, "AM" if hour < 12 else "PM"


def checkout_line_item(booking: Booking) -> str:
    """The PayMongo line item, e.g. "Tennis Court 2 · Tennis · Sat 18 Oct, 6–8 PM". It goes to
    PayMongo verbatim, so it is built from the court, the sport and the time only: never customer
    data."""
    start = booking.starts_at.astimezone(TIME_ZONE)
    first, first_half = _hour_label(start.hour)
    last, last_half = _hour_label(start.hour + booking.hours)
    span = (
        f"{first}–{last} {last_half}"
        if first_half == last_half
        else f"{first} {first_half}–{last} {last_half}"
    )
    day = f"{start:%a} {start.day} {start:%b}"
    return f"{booking.court.name} · {Sport(booking.sport).label} · {day}, {span}"


@require_service_token
@require_POST
def create_booking(request):
    try:
        body = _json_body(request)
    except _BadBody as bad:
        return bad.response

    customer = body.get("customer")
    if not isinstance(customer, dict):
        customer = {}
    court_code = body.get("court")
    sport = body.get("sport")
    coverage = body.get("coverage")
    raw_date = body.get("date")
    day = _parse_date(raw_date) if isinstance(raw_date, str) else None
    start_hour = body.get("start_hour")
    hours = body.get("hours")
    name = _name(customer.get("name"))
    email = _email(customer.get("email"))
    mobile = _mobile(customer.get("mobile"))
    client_ip = _client_ip(body.get("client_ip"))

    court = None
    if _text(court_code):
        court = Court.objects.filter(code=court_code, is_active=True).first()

    fields = []
    for field, ok in (
        ("court", court is not None),
        ("sport", isinstance(sport, str) and sport in SPORTS),
        ("coverage", isinstance(coverage, str) and coverage in Coverage.values),
        ("date", day is not None),
        ("start_hour", _is_int(start_hour)),
        ("hours", _is_int(hours)),
        ("customer.name", name is not None),
        ("customer.email", email is not None),
        ("customer.mobile", mobile is not None),
        ("consent", body.get("consent") is True),
        ("client_ip", client_ip is not None),
    ):
        if not ok:
            fields.append(field)
    if fields:
        return _invalid(fields)

    if not hit("booking_create", client_ip, limit=CREATE_LIMIT, window_seconds=WINDOW_SECONDS):
        return json_response({"error": "rate_limited"}, status=429)

    now = timezone.now()
    active_holds = Booking.objects.filter(
        status=Status.PENDING, hold_expires_at__gt=now, customer_email=email
    ).count()
    if active_holds >= MAX_ACTIVE_HOLDS:
        return json_response({"error": "too_many_holds"}, status=429)

    # Validates the booking rules, quotes the price on the server and claims the slots; it
    # commits before it returns.
    try:
        booking = create_hold(
            court=court,
            sport=sport,
            coverage=coverage,
            day=day,
            start_hour=start_hour,
            hours=hours,
            customer=Customer(name=name, email=email, mobile=mobile),
            now=now,
        )
    except SlotTaken:
        return json_response({"error": "slot_taken"}, status=409)
    except BookingRuleError as error:
        return json_response({"error": error.code}, status=400)

    # Outside any transaction: the hold has committed.
    try:
        with get_client() as client:
            session = client.create_checkout_session(
                booking_id=str(booking.id),
                line_item_name=checkout_line_item(booking),
                amount_centavos=booking.price_centavos,
                description=f"Kalaro Courts booking {booking.reference} (test mode)",
                success_url=f"{settings.SITE_URL}/book/success",
                cancel_url=f"{settings.SITE_URL}/book/cancelled",
            )
    except (PayMongoError, PaymentsConfigError) as error:
        release(booking, status=Status.EXPIRED)
        log_error("booking.checkout_failed", error, ref=booking.reference)
        return json_response({"error": "payments_unavailable"}, status=503)

    booking.checkout_session_id = session.id
    booking.save(update_fields=["checkout_session_id", "updated_at"])
    return json_response(
        {
            "reference": booking.reference,
            "checkout_url": session.checkout_url,
            "checkout_session_id": session.id,
            "hold_expires_at": iso_local(booking.hold_expires_at),
            "price_centavos": booking.price_centavos,
        },
        status=201,
    )


def _checkout_session_id(request):
    """The body's `checkout_session_id`, or an error response. A malformed ID is passed on:
    `payments.confirm` answers `not_found` without calling PayMongo."""
    body = _json_body(request)
    value = body.get("checkout_session_id")
    if not isinstance(value, str) or not value:
        raise _BadBody(_invalid(["checkout_session_id"]))
    return value


@require_service_token
@require_POST
def checkout_confirm(request):
    try:
        session_id = _checkout_session_id(request)
    except _BadBody as bad:
        return bad.response

    # Not in a transaction: it may read the session from PayMongo.
    result = check_checkout(session_id)
    status = result.status
    booking = result.booking
    if (
        status == "pending"
        and booking is not None
        and booking.status
        in (
            Status.EXPIRED,
            Status.CANCELLED,
        )
    ):
        # No paid payment, and the hold is gone: say so, rather than "still processing".
        status = str(booking.status)
    return json_response(
        {"status": status, "booking": None if booking is None else booking_summary(booking)}
    )


@require_service_token
@require_POST
def checkout_release(request):
    try:
        session_id = _checkout_session_id(request)
    except _BadBody as bad:
        return bad.response
    return json_response({"status": release_checkout(session_id)})


@require_service_token
@require_POST
def booking_lookup(request):
    try:
        body = _json_body(request)
    except _BadBody as bad:
        return bad.response

    reference = _text(body.get("reference"))
    email = _text(body.get("email"))
    client_ip = _client_ip(body.get("client_ip"))
    fields = []
    if not reference:
        fields.append("reference")
    if not email:
        fields.append("email")
    if client_ip is None:
        fields.append("client_ip")
    if fields:
        return _invalid(fields)

    if not hit("booking_lookup", client_ip, limit=LOOKUP_LIMIT, window_seconds=WINDOW_SECONDS):
        return json_response({"error": "rate_limited"}, status=429)

    # One query on both keys, so a wrong reference and a wrong email look the same.
    booking = (
        Booking.objects.select_related("court")
        .filter(
            reference=reference.upper(),
            customer_email=email.lower(),
            anonymized_at__isnull=True,
        )
        .first()
    )
    if booking is None:
        return json_response({"error": "not_found"}, status=404)
    return json_response({"booking": booking_summary(booking)})

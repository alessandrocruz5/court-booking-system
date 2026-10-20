"""PayMongo webhooks: check the `Paymongo-Signature` header against the raw request body, then read
the event. The header is `t=<unix seconds>,te=<test-mode signature>,li=<live-mode signature>`, and
each signature is the hex HMAC-SHA256 of `<t>.<raw body>` keyed with the webhook's secret.

Test mode only: `te` is the only signature compared, so a live-mode delivery (empty `te`) never
verifies.
"""

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass

from .paymongo import PayMongoError

SIGNATURE_HEADER = "Paymongo-Signature"
# The same header in Django's `request.META`.
SIGNATURE_META_KEY = "HTTP_PAYMONGO_SIGNATURE"

# A delivery signed further than this from now, either way, is refused as a replay.
SIGNATURE_TOLERANCE_SECONDS = 300

# The only event the app acts on.
CHECKOUT_SESSION_PAID = "checkout_session.payment.paid"

# re.ASCII: `\d` would otherwise accept non-ASCII digits.
_TIMESTAMP = re.compile(r"^\d{1,12}$", re.ASCII)
_HEX_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class SignatureCheck:
    ok: bool
    # `missing`, `malformed`, `stale` or `mismatch`; None when ok.
    reason: str | None = None


def _parse_header(header: str) -> dict[str, str] | None:
    """`k=v,k=v` into a dict, or None when a part has no `=`, has no key, or a key repeats. Empty
    parts are skipped."""
    parts: dict[str, str] = {}
    for part in header.split(","):
        if not part.strip():
            continue
        key, separator, value = part.partition("=")
        key = key.strip()
        if not separator or not key or key in parts:
            return None
        parts[key] = value.strip()
    return parts


def verify_signature(
    *, header: str | None, raw_body: bytes, secret: str, now: int | None = None
) -> SignatureCheck:
    """Whether `raw_body` was signed by PayMongo with `secret` within the last few minutes. The
    signatures are compared in constant time. `raw_body` must be the body exactly as received,
    before any JSON parsing. `now` is unix seconds and defaults to the current time."""
    if not header:
        return SignatureCheck(False, "missing")

    parts = _parse_header(header)
    timestamp = parts.get("t") if parts is not None else None
    signature = parts.get("te") if parts is not None else None
    if (
        not timestamp
        or not _TIMESTAMP.fullmatch(timestamp)
        or not signature
        or not _HEX_SHA256.fullmatch(signature)
    ):
        return SignatureCheck(False, "malformed")

    current = int(time.time()) if now is None else now
    if abs(current - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
        return SignatureCheck(False, "stale")

    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
    ).digest()
    # Both are 32 bytes: `signature` is 64 hex digits.
    if hmac.compare_digest(expected, bytes.fromhex(signature)):
        return SignatureCheck(True, None)
    return SignatureCheck(False, "mismatch")


@dataclass(frozen=True)
class WebhookEvent:
    # PayMongo's event ID (`evt_…`).
    id: str
    # e.g. `checkout_session.payment.paid`.
    type: str
    livemode: bool
    # The resource the event is about: a checkout session for `checkout_session.payment.paid`.
    data: object


def parse_event(raw_body: bytes) -> WebhookEvent:
    """Read a verified raw body as a PayMongo event. Raises `PayMongoError`, never quoting the
    body."""
    try:
        payload = json.loads(raw_body)
    except ValueError, RecursionError:
        raise PayMongoError("PayMongo event is not JSON") from None

    data = payload.get("data") if isinstance(payload, dict) else None
    attributes = data.get("attributes") if isinstance(data, dict) else None
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("id"), str)
        or not isinstance(attributes, dict)
        or not isinstance(attributes.get("type"), str)
        or not isinstance(attributes.get("livemode"), bool)
    ):
        raise PayMongoError("Unexpected PayMongo event")
    return WebhookEvent(
        id=data["id"],
        type=attributes["type"],
        livemode=attributes["livemode"],
        data=attributes.get("data"),
    )

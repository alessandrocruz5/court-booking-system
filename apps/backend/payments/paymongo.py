"""PayMongo Hosted Checkout: create a checkout session, send the customer to its `checkout_url`,
read it back later to see whether it was paid, or expire it. Amounts are integer centavos, currency
PHP.

Errors carry an HTTP status and PayMongo's error codes only, never a request or response body, so
nothing a customer typed can reach a log (RA 10173).
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from .env import TEST_SECRET_KEY, get_secret_key

API_URL = "https://api.paymongo.com/v1"
TIMEOUT_SECONDS = 10.0

# Offered on the hosted checkout page. All of them can be simulated in test mode.
PAYMENT_METHOD_TYPES = ("card", "gcash", "paymaya", "grab_pay")

CHECKOUT_SESSION_ID = re.compile(r"^cs_[A-Za-z0-9]+$")

_CHECKOUT_HOST = "checkout.paymongo.com"


def is_checkout_session_id(value: object) -> bool:
    """A well-formed checkout session ID (`cs_…`), safe to put in a URL path."""
    return isinstance(value, str) and CHECKOUT_SESSION_ID.fullmatch(value) is not None


class PayMongoError(Exception):
    """A PayMongo call failed. `status` is the HTTP status, or 0 when no usable response arrived;
    `codes` are PayMongo error codes such as `parameter_invalid`. The `detail` text is dropped."""

    def __init__(self, message: str, status: int = 0, codes: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.status = status
        self.codes = codes


@dataclass(frozen=True)
class Payment:
    id: str
    # `paid`, `pending` or `failed`.
    status: str
    amount_centavos: int
    currency: str
    fee_centavos: int
    net_centavos: int
    # The payment source type: `card`, `gcash`, `paymaya`, …
    method: str
    paid_at: datetime | None
    livemode: bool


@dataclass(frozen=True)
class CheckoutSession:
    id: str
    checkout_url: str
    # `active` or `expired`.
    status: str
    livemode: bool
    metadata: dict[str, str]
    # Filled in only when the session is read with the secret key.
    payments: tuple[Payment, ...]


class _Shape(Exception):
    """Internal: the resource doesn't have the expected shape."""


def _obj(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _Shape
    return value


def _str(value: object) -> str:
    if not isinstance(value, str):
        raise _Shape
    return value


def _int(value: object) -> int:
    # bool is an int subclass; JSON true is not an amount.
    if type(value) is not int:
        raise _Shape
    return value


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise _Shape
    return value


def _parse_payment(resource: object) -> Payment:
    r = _obj(resource)
    a = _obj(r.get("attributes"))
    paid_at = a.get("paid_at")
    source = a.get("source")
    method = "unknown" if source is None else _str(_obj(source).get("type"))
    return Payment(
        id=_str(r.get("id")),
        status=_str(a.get("status")),
        amount_centavos=_int(a.get("amount")),
        currency=_str(a.get("currency")),
        fee_centavos=_int(a.get("fee")),
        net_centavos=_int(a.get("net_amount")),
        method=method,
        paid_at=None if paid_at is None else datetime.fromtimestamp(_int(paid_at), tz=UTC),
        livemode=_bool(a.get("livemode")),
    )


def parse_checkout_session(resource: object) -> CheckoutSession:
    """Map a PayMongo checkout session resource (`{id, attributes}`) to a `CheckoutSession`. The
    webhook's `data.attributes.data` has the same shape."""
    try:
        r = _obj(resource)
        session_id = _str(r.get("id"))
        if not CHECKOUT_SESSION_ID.fullmatch(session_id):
            raise _Shape
        a = _obj(r.get("attributes"))
        metadata = a.get("metadata")
        metadata = {} if metadata is None else _obj(metadata)
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()):
            raise _Shape
        payments = a.get("payments")
        if payments is None:
            payments = []
        elif not isinstance(payments, list):
            raise _Shape
        return CheckoutSession(
            id=session_id,
            checkout_url=_str(a.get("checkout_url")),
            status=_str(a.get("status")),
            livemode=_bool(a.get("livemode")),
            metadata=dict(metadata),
            payments=tuple(_parse_payment(p) for p in payments),
        )
    except _Shape, OverflowError, OSError, ValueError:
        # OverflowError/OSError/ValueError: a `paid_at` out of datetime's range.
        raise PayMongoError("Unexpected PayMongo checkout session") from None


def _error_codes(body: object) -> tuple[str, ...]:
    """PayMongo's error codes, all or nothing, as with fun-run's schema. `detail` is dropped."""
    if not isinstance(body, dict) or not isinstance(body.get("errors"), list):
        return ()
    codes = []
    for error in body["errors"]:
        if not isinstance(error, dict) or not isinstance(error.get("code"), str):
            return ()
        codes.append(error["code"])
    return tuple(codes)


def _is_paymongo_checkout_url(value: str) -> bool:
    # Refuse anything a browser and urlsplit might read differently: backslashes, whitespace,
    # control characters, and user info (`a@b`).
    if "\\" in value or any(ord(ch) <= 0x20 or ord(ch) == 0x7F for ch in value):
        return False
    try:
        url = urlsplit(value)
        return url.scheme == "https" and "@" not in url.netloc and url.hostname == _CHECKOUT_HOST
    except ValueError:
        return False


class PayMongoClient:
    """A Hosted Checkout client. Accepts test secret keys (`sk_test_…`) only, whatever the
    environment says. `transport` is for tests (`httpx.MockTransport`)."""

    def __init__(self, secret_key: str, *, transport: httpx.BaseTransport | None = None) -> None:
        if not isinstance(secret_key, str) or not TEST_SECRET_KEY.fullmatch(secret_key):
            raise ValueError("The PayMongo client accepts test secret keys (sk_test_…) only")
        self._http = httpx.Client(
            base_url=API_URL,
            auth=httpx.BasicAuth(secret_key, ""),
            headers={"Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> PayMongoClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _request(self, method: str, path: str, body: object = None) -> CheckoutSession:
        try:
            if body is None:
                response = self._http.request(method, path)
            else:
                response = self._http.request(method, path, json=body)
        except httpx.HTTPError:
            # Transport failure or timeout. `from None`: the cause adds nothing safe to log.
            raise PayMongoError("PayMongo request failed") from None

        try:
            payload: object = response.json()
        except ValueError:
            payload = None
        status = response.status_code
        if not response.is_success:
            raise PayMongoError(f"PayMongo responded {status}", status, _error_codes(payload))
        if not isinstance(payload, dict) or "data" not in payload:
            raise PayMongoError("Unexpected PayMongo response", status)
        return parse_checkout_session(payload["data"])

    def create_checkout_session(
        self,
        *,
        booking_id: str,
        line_item_name: str,
        amount_centavos: int,
        description: str,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession:
        """Create a checkout session for one line item. `booking_id` is the only metadata PayMongo
        gets, so no personal data leaves us. The amount is the booking's price snapshot."""
        if type(amount_centavos) is not int or amount_centavos <= 0:
            raise ValueError("Checkout amount must be a positive whole number of centavos")
        session = self._request(
            "POST",
            "/checkout_sessions",
            {
                "data": {
                    "attributes": {
                        "line_items": [
                            {
                                "name": line_item_name,
                                "amount": amount_centavos,
                                "currency": "PHP",
                                "quantity": 1,
                            }
                        ],
                        "payment_method_types": list(PAYMENT_METHOD_TYPES),
                        "description": description,
                        "success_url": success_url,
                        "cancel_url": cancel_url,
                        "send_email_receipt": False,
                        "show_description": True,
                        "show_line_items": True,
                        "metadata": {"booking_id": booking_id},
                    }
                }
            },
        )
        if not _is_paymongo_checkout_url(session.checkout_url):
            raise PayMongoError("Unexpected checkout URL", 200)
        return session

    def retrieve_checkout_session(self, session_id: str) -> CheckoutSession:
        """Read a session back, with its payments. Raises if PayMongo returns another session."""
        if not is_checkout_session_id(session_id):
            raise ValueError("Not a checkout session ID")
        session = self._request("GET", f"/checkout_sessions/{session_id}")
        if session.id != session_id:
            raise PayMongoError("PayMongo returned another session", 200)
        return session

    def expire_checkout_session(self, session_id: str) -> CheckoutSession:
        """Expire a session ("Expire a Checkout Session" in PayMongo's API reference), which also
        cancels its payment intent."""
        if not is_checkout_session_id(session_id):
            raise ValueError("Not a checkout session ID")
        session = self._request("POST", f"/checkout_sessions/{session_id}/expire")
        if session.id != session_id:
            raise PayMongoError("PayMongo returned another session", 200)
        return session


def get_client() -> PayMongoClient:
    """A client for `PAYMONGO_SECRET_KEY`, built per call: the key is never read at import."""
    return PayMongoClient(get_secret_key())

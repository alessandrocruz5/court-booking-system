import copy
import hashlib
import hmac
import json
import time

import pytest

from payments import webhook
from payments.paymongo import PayMongoError, parse_checkout_session
from payments.webhook import (
    CHECKOUT_SESSION_PAID,
    SIGNATURE_TOLERANCE_SECONDS,
    SignatureCheck,
    WebhookEvent,
    parse_event,
    verify_signature,
)

SECRET = "whsk_testsecret"
T = 1_496_734_173
OK = SignatureCheck(True, None)


def sign(raw_body: bytes, t: int | str = T, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), f"{t}.".encode() + raw_body, hashlib.sha256).hexdigest()


def verify(header, raw_body: bytes, now: int = T) -> SignatureCheck:
    return verify_signature(header=header, raw_body=raw_body, secret=SECRET, now=now)


def test_constants():
    assert webhook.SIGNATURE_HEADER == "Paymongo-Signature"
    assert webhook.SIGNATURE_META_KEY == "HTTP_PAYMONGO_SIGNATURE"
    assert SIGNATURE_TOLERANCE_SECONDS == 300
    assert CHECKOUT_SESSION_PAID == "checkout_session.payment.paid"


def test_matches_a_fixed_vector():
    # Hex HMAC-SHA256 of `t.body` (computed with openssl, carried over from fun-run).
    raw_body = b'{"data":{"id":"evt_test1"}}'
    te = "99891e41d1b4082f7f6b8da075fa9b698cd7551d59d592587a3dcb659e5eea65"
    assert verify(f"t={T},te={te},li=", raw_body) == OK


def test_accepts_the_test_mode_header_comparing_in_constant_time(monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(webhook.hmac, "compare_digest", spy)
    raw_body = b'{"data":{"id":"evt_1","attributes":{"type":"x"}}}'
    assert verify(f"t={T},te={sign(raw_body)},li=", raw_body) == OK
    assert len(calls) == 1


def test_accepts_any_key_order_spaces_and_upper_case_hex():
    raw_body = b"{}"
    assert verify(f" li= , te={sign(raw_body).upper()} , t={T},", raw_body) == OK


@pytest.mark.parametrize("t", [T - SIGNATURE_TOLERANCE_SECONDS, T + SIGNATURE_TOLERANCE_SECONDS])
def test_accepts_a_timestamp_at_the_edge_of_the_window(t):
    assert verify(f"t={t},te={sign(b'{}', t)},li=", b"{}") == OK


@pytest.mark.parametrize(
    "t", [T - SIGNATURE_TOLERANCE_SECONDS - 1, T + SIGNATURE_TOLERANCE_SECONDS + 1]
)
def test_refuses_a_correctly_signed_timestamp_301_seconds_off(t):
    assert verify(f"t={t},te={sign(b'{}', t)},li=", b"{}") == SignatureCheck(False, "stale")


@pytest.mark.parametrize("header", [None, ""])
def test_refuses_a_missing_header(header):
    assert verify(header, b"{}") == SignatureCheck(False, "missing")


@pytest.mark.parametrize(
    "header",
    [
        pytest.param(f"t={T},li=", id="no te"),
        pytest.param(f"t={T},te=,li={sign(b'{}')}", id="an empty te (a live-mode delivery)"),
        pytest.param(f"te={sign(b'{}')},li=", id="no t"),
        pytest.param(f"t=abc,te={sign(b'{}', 'abc')},li=", id="a non-numeric t"),
        pytest.param(f"t=-{T},te={sign(b'{}', f'-{T}')},li=", id="a negative t"),
        pytest.param("t=١٤٩٦٧٣٤١٧٣,te=" + sign(b"{}") + ",li=", id="non-ascii digits in t"),
        pytest.param(f"t={T},te={'z' * 64},li=", id="a te that isn't hex"),
        pytest.param(f"t={T},te={sign(b'{}')[:62]},li=", id="a short te"),
        pytest.param(f"t={T},te={'0' * 64},te={sign(b'{}')},li=", id="a repeated te"),
        pytest.param(f"t={T},t={T},te={sign(b'{}')},li=", id="a repeated t"),
        pytest.param(f"t={T},te={sign(b'{}')},li", id="a part without ="),
        pytest.param(f"t={T},={sign(b'{}')},te={sign(b'{}')}", id="an empty key"),
        pytest.param(sign(b"{}"), id="a bare signature"),
    ],
)
def test_refuses_a_malformed_header_without_comparing(header, monkeypatch):
    def fail(*_args):
        raise AssertionError("compare_digest must not run on a malformed header")

    monkeypatch.setattr(webhook.hmac, "compare_digest", fail)
    assert verify(header, b"{}") == SignatureCheck(False, "malformed")


@pytest.mark.parametrize(
    ("header", "raw_body"),
    [
        pytest.param(f"t={T},te={sign(b'{}', T, 'whsk_other')},li=", b"{}", id="another secret"),
        pytest.param(f"t={T},te={sign(b'{"a":1}')},li=", b'{"a":2}', id="body changed by a byte"),
        pytest.param(f"t={T},te={sign(b'{"a": 1}')},li=", b'{"a":1}', id="re-serialized body"),
        pytest.param(f"t={T + 1},te={sign(b'{}', T)},li=", b"{}", id="a changed timestamp"),
        pytest.param(f"t={T},te={'0' * 64},li={sign(b'{}')}", b"{}", id="right signature in li"),
    ],
)
def test_refuses_a_mismatched_signature(header, raw_body):
    assert verify(header, raw_body) == SignatureCheck(False, "mismatch")


def test_defaults_to_the_current_time():
    now = int(time.time())
    header = f"t={now},te={sign(b'{}', now)},li="
    assert verify_signature(header=header, raw_body=b"{}", secret=SECRET) == OK
    old = f"t={T},te={sign(b'{}')},li="
    assert verify_signature(header=old, raw_body=b"{}", secret=SECRET) == SignatureCheck(
        False, "stale"
    )


CHECKOUT_SESSION = {
    "id": "cs_test1",
    "type": "checkout_session",
    "attributes": {
        "checkout_url": "https://checkout.paymongo.com/cs_test1_client_x",
        "status": "active",
        "livemode": False,
        "metadata": {"booking_id": "booking-1"},
        "payments": [
            {
                "id": "pay_test1",
                "type": "payment",
                "attributes": {
                    "amount": 100_000,
                    "currency": "PHP",
                    "fee": 2_500,
                    "net_amount": 97_500,
                    "status": "paid",
                    "livemode": False,
                    "paid_at": 1_791_532_800,
                    "source": {"id": "src_x", "type": "gcash"},
                },
            }
        ],
    },
}

PAID_EVENT = {
    "data": {
        "id": "evt_test1",
        "type": "event",
        "attributes": {
            "type": CHECKOUT_SESSION_PAID,
            "livemode": False,
            "data": CHECKOUT_SESSION,
            "previous_data": {},
            "created_at": T,
            "updated_at": T,
        },
    }
}


def test_parse_event_reads_the_event_whose_data_is_the_checkout_session():
    event = parse_event(json.dumps(PAID_EVENT).encode())
    assert event == WebhookEvent(
        id="evt_test1", type=CHECKOUT_SESSION_PAID, livemode=False, data=CHECKOUT_SESSION
    )
    payment = parse_checkout_session(event.data).payments[0]
    assert (payment.method, payment.fee_centavos, payment.net_centavos) == ("gcash", 2_500, 97_500)


def test_parse_event_reads_livemode_as_sent():
    live = copy.deepcopy(PAID_EVENT)
    live["data"]["attributes"]["livemode"] = True
    assert parse_event(json.dumps(live).encode()).livemode is True


@pytest.mark.parametrize(
    ("raw_body", "message"),
    [
        pytest.param(b"juana@example.test", "PayMongo event is not JSON", id="not JSON"),
        pytest.param(b"\xff\xfejuana", "PayMongo event is not JSON", id="not UTF-8"),
        pytest.param(b"[" * 100_000, "PayMongo event is not JSON", id="too deeply nested"),
        pytest.param(b"[]", "Unexpected PayMongo event", id="an array"),
        pytest.param(
            json.dumps({"data": {"id": "evt_1"}}).encode(),
            "Unexpected PayMongo event",
            id="no attributes",
        ),
        pytest.param(
            json.dumps({"data": {"id": "evt_1", "attributes": {"type": "x"}}}).encode(),
            "Unexpected PayMongo event",
            id="no livemode",
        ),
        pytest.param(
            json.dumps(
                {"data": {"id": 1, "attributes": {"type": "x", "livemode": False}}}
            ).encode(),
            "Unexpected PayMongo event",
            id="a numeric id",
        ),
        pytest.param(
            json.dumps({"juana": "juana@example.test"}).encode(),
            "Unexpected PayMongo event",
            id="wrong shape quoting personal data",
        ),
    ],
)
def test_parse_event_refuses_a_bad_body_without_quoting_it(raw_body, message):
    with pytest.raises(PayMongoError) as excinfo:
        parse_event(raw_body)
    assert str(excinfo.value) == message
    assert "juana" not in repr(excinfo.value)
    assert excinfo.value.__cause__ is None

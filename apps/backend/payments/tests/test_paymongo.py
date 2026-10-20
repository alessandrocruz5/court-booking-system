import base64
import json
import math
from datetime import UTC, datetime

import httpx
import pytest

from payments.paymongo import (
    PAYMENT_METHOD_TYPES,
    CheckoutSession,
    Payment,
    PayMongoClient,
    PayMongoError,
    is_checkout_session_id,
    parse_checkout_session,
)

SECRET_KEY = "sk_test_abc123"
BOOKING_ID = "0b9f6c1e-1111-4222-8333-444455556666"


def session_resource(session_id="cs_test1", **attributes):
    return {
        "id": session_id,
        "type": "checkout_session",
        "attributes": {
            "checkout_url": f"https://checkout.paymongo.com/{session_id}_client_x#cGtfdGVzdA==",
            "status": "active",
            "livemode": False,
            "metadata": {"booking_id": "booking-1"},
            "payments": [],
            **attributes,
        },
    }


PAID_PAYMENT = {
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
        "source": {"id": "card_x", "type": "card", "brand": "visa", "last4": "4345"},
    },
}

INPUT = {
    "booking_id": BOOKING_ID,
    "line_item_name": "Kalaro Courts · Tennis court 1",
    "amount_centavos": 100_000,
    "description": "Fictional venue · Test mode, no real payments",
    "success_url": "https://kalaro.test/book/success",
    "cancel_url": "https://kalaro.test/book/cancelled",
}


class Recorder:
    """A mock transport that records requests and answers with a fixed response or error."""

    def __init__(self, response: httpx.Response | Exception):
        self.response = response
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    @property
    def body(self):
        return json.loads(self.requests[0].content)


def client_returning(response: httpx.Response | Exception):
    recorder = Recorder(response)
    return recorder, PayMongoClient(SECRET_KEY, transport=httpx.MockTransport(recorder))


def ok(data, status=200):
    return httpx.Response(status, json={"data": data})


# --- create_checkout_session -----------------------------------------------------------------


def test_create_posts_one_php_line_item_with_basic_auth():
    recorder, client = client_returning(ok(session_resource()))
    session = client.create_checkout_session(**INPUT)

    request = recorder.requests[0]
    assert str(request.url) == "https://api.paymongo.com/v1/checkout_sessions"
    assert request.method == "POST"
    expected_auth = base64.b64encode(f"{SECRET_KEY}:".encode()).decode()
    assert request.headers["authorization"] == f"Basic {expected_auth}"
    attributes = recorder.body["data"]["attributes"]
    assert attributes["line_items"] == [
        {"name": INPUT["line_item_name"], "amount": 100_000, "currency": "PHP", "quantity": 1}
    ]
    assert attributes["payment_method_types"] == list(PAYMENT_METHOD_TYPES)
    assert attributes["payment_method_types"] == ["card", "gcash", "paymaya", "grab_pay"]
    assert attributes["description"] == INPUT["description"]
    assert attributes["success_url"] == INPUT["success_url"]
    assert attributes["cancel_url"] == INPUT["cancel_url"]
    assert attributes["send_email_receipt"] is False
    assert attributes["show_description"] is True
    assert attributes["show_line_items"] is True

    assert session.id == "cs_test1"
    assert session.checkout_url == "https://checkout.paymongo.com/cs_test1_client_x#cGtfdGVzdA=="
    assert session.livemode is False
    assert session.payments == ()


def test_create_sends_the_booking_id_as_the_only_metadata():
    recorder, client = client_returning(ok(session_resource()))
    client.create_checkout_session(**INPUT)
    attributes = recorder.body["data"]["attributes"]
    assert attributes["metadata"] == {"booking_id": BOOKING_ID}
    assert "billing" not in attributes
    assert "customer_email" not in attributes


@pytest.mark.parametrize("amount", [0, -1, 1.5, math.nan, True, "100"])
def test_create_refuses_a_bad_amount_without_calling_paymongo(amount):
    recorder, client = client_returning(ok(session_resource()))
    with pytest.raises(ValueError):
        client.create_checkout_session(**{**INPUT, "amount_centavos": amount})
    assert recorder.requests == []


def test_create_reports_a_paymongo_error_by_status_and_code_only():
    _, client = client_returning(
        httpx.Response(
            400, json={"errors": [{"code": "parameter_invalid", "detail": "secret stuff"}]}
        )
    )
    with pytest.raises(PayMongoError) as excinfo:
        client.create_checkout_session(**INPUT)
    assert excinfo.value.status == 400
    assert excinfo.value.codes == ("parameter_invalid",)
    assert "secret stuff" not in str(excinfo.value)
    assert "secret stuff" not in repr(excinfo.value)


def test_create_reports_an_error_without_a_json_body():
    _, client = client_returning(httpx.Response(502, text="<html>Bad gateway</html>"))
    with pytest.raises(PayMongoError) as excinfo:
        client.create_checkout_session(**INPUT)
    assert excinfo.value.status == 502
    assert excinfo.value.codes == ()


@pytest.mark.parametrize(
    "error",
    [httpx.ReadTimeout("timed out"), httpx.ConnectError("connection refused")],
)
def test_create_wraps_a_timeout_or_network_failure(error):
    _, client = client_returning(error)
    with pytest.raises(PayMongoError, match="PayMongo request failed") as excinfo:
        client.create_checkout_session(**INPUT)
    assert excinfo.value.status == 0
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize(
    "checkout_url",
    [
        "https://evil.test/pay",
        "http://checkout.paymongo.com/cs_test1",
        "https://checkout.paymongo.com.evil.test/cs_test1",
        "https://checkout.paymongo.com@evil.test/cs_test1",
        "https://evil.test\\@checkout.paymongo.com/cs_test1",
        "javascript:alert(1)",
        "not a url",
    ],
)
def test_create_refuses_a_checkout_url_that_isnt_paymongos(checkout_url):
    _, client = client_returning(ok(session_resource(checkout_url=checkout_url)))
    with pytest.raises(PayMongoError):
        client.create_checkout_session(**INPUT)


@pytest.mark.parametrize("payload", [{"data": {"id": "nope"}}, [], {"nodata": {}}])
def test_create_refuses_a_response_it_cant_read(payload):
    _, client = client_returning(httpx.Response(200, json=payload))
    with pytest.raises(PayMongoError):
        client.create_checkout_session(**INPUT)


def test_create_refuses_a_non_json_success():
    _, client = client_returning(httpx.Response(200, text="ok"))
    with pytest.raises(PayMongoError, match="Unexpected PayMongo response") as excinfo:
        client.create_checkout_session(**INPUT)
    assert excinfo.value.status == 200


@pytest.mark.parametrize("status", [200, 500])
def test_create_refuses_a_deeply_nested_body_as_a_paymongo_error(status):
    # json.loads raises RecursionError, not ValueError, on a body nested this deep.
    nested = "[" * 200_000 + "]" * 200_000
    _, client = client_returning(httpx.Response(status, text=nested))
    with pytest.raises(PayMongoError) as excinfo:
        client.create_checkout_session(**INPUT)
    assert excinfo.value.status == status
    assert excinfo.value.codes == ()


# --- retrieve_checkout_session ---------------------------------------------------------------


def test_retrieve_gets_the_session_with_its_payments():
    recorder, client = client_returning(ok(session_resource(payments=[PAID_PAYMENT])))
    session = client.retrieve_checkout_session("cs_test1")

    request = recorder.requests[0]
    assert str(request.url) == "https://api.paymongo.com/v1/checkout_sessions/cs_test1"
    assert request.method == "GET"
    assert request.content == b""
    assert session.payments == (
        Payment(
            id="pay_test1",
            status="paid",
            amount_centavos=100_000,
            currency="PHP",
            fee_centavos=2_500,
            net_centavos=97_500,
            method="card",
            paid_at=datetime.fromtimestamp(1_791_532_800, tz=UTC),
            livemode=False,
        ),
    )


@pytest.mark.parametrize(
    "session_id", ["", "cs_", "pay_test1", "cs_test1/../../payments", "cs_test 1", "cs_x\n", None]
)
def test_retrieve_refuses_a_bad_id_without_calling_paymongo(session_id):
    recorder, client = client_returning(ok(session_resource()))
    with pytest.raises(ValueError):
        client.retrieve_checkout_session(session_id)
    assert recorder.requests == []


def test_retrieve_refuses_a_different_session_than_the_one_asked_for():
    _, client = client_returning(ok(session_resource("cs_other")))
    with pytest.raises(PayMongoError):
        client.retrieve_checkout_session("cs_test1")


# --- expire_checkout_session -----------------------------------------------------------------


def test_expire_posts_to_expire_with_no_body():
    recorder, client = client_returning(ok(session_resource(status="expired")))
    session = client.expire_checkout_session("cs_test1")

    request = recorder.requests[0]
    assert str(request.url) == "https://api.paymongo.com/v1/checkout_sessions/cs_test1/expire"
    assert request.method == "POST"
    assert request.content == b""
    assert session.status == "expired"


def test_expire_refuses_a_bad_id_without_calling_paymongo():
    recorder, client = client_returning(ok(session_resource()))
    with pytest.raises(ValueError):
        client.expire_checkout_session("cs_test1/../x")
    assert recorder.requests == []


def test_expire_refuses_a_different_session():
    _, client = client_returning(ok(session_resource("cs_other")))
    with pytest.raises(PayMongoError):
        client.expire_checkout_session("cs_test1")


# --- parse_checkout_session ------------------------------------------------------------------


def test_parse_maps_a_paid_payment():
    session = parse_checkout_session(session_resource(payments=[PAID_PAYMENT]))
    assert session == CheckoutSession(
        id="cs_test1",
        checkout_url="https://checkout.paymongo.com/cs_test1_client_x#cGtfdGVzdA==",
        status="active",
        livemode=False,
        metadata={"booking_id": "booking-1"},
        payments=(
            Payment(
                id="pay_test1",
                status="paid",
                amount_centavos=100_000,
                currency="PHP",
                fee_centavos=2_500,
                net_centavos=97_500,
                method="card",
                paid_at=datetime(2026, 10, 9, 8, 0, tzinfo=UTC),
                livemode=False,
            ),
        ),
    )
    assert session.payments[0].paid_at.tzinfo is UTC


def test_parse_defaults_missing_metadata_and_payments_and_an_unknown_source():
    attributes = {k: v for k, v in PAID_PAYMENT["attributes"].items() if k != "source"}
    session = parse_checkout_session(
        session_resource(
            metadata=None,
            payments=[{**PAID_PAYMENT, "attributes": {**attributes, "paid_at": None}}],
        )
    )
    assert session.metadata == {}
    assert session.payments[0].method == "unknown"
    assert session.payments[0].paid_at is None

    resource = session_resource()
    del resource["attributes"]["payments"]
    assert parse_checkout_session(resource).payments == ()


@pytest.mark.parametrize(
    "resource",
    [
        None,
        [],
        session_resource("pay_test1"),
        session_resource(livemode="false"),
        session_resource(metadata={"booking_id": 1}),
        session_resource(payments={}),
        session_resource(payments=[{"id": "pay_1", "attributes": {}}]),
        session_resource(
            payments=[{**PAID_PAYMENT, "attributes": {**PAID_PAYMENT["attributes"], "amount": 1.5}}]
        ),
        session_resource(
            payments=[
                {**PAID_PAYMENT, "attributes": {**PAID_PAYMENT["attributes"], "paid_at": 10**20}}
            ]
        ),
    ],
)
def test_parse_refuses_an_unexpected_shape(resource):
    with pytest.raises(PayMongoError, match="Unexpected PayMongo checkout session"):
        parse_checkout_session(resource)


# --- is_checkout_session_id ------------------------------------------------------------------


def test_is_checkout_session_id_accepts_only_cs_ids():
    assert is_checkout_session_id("cs_CbFCTDfxvMFNjwjVi26Uzhtj")
    assert not is_checkout_session_id("cs_a/b")
    assert not is_checkout_session_id("cs_abc\n")
    assert not is_checkout_session_id(None)
